import os
import time
import concurrent.futures
import io
import logging
import json
from datetime import datetime
from urllib.parse import urlencode
from datetime import timezone
import random
import traceback

from open_webui.env import SRC_LOG_LEVELS

from open_webui.utils.data.data_ingestion import upload_to_gcs, download_from_gcs, list_gcs_files, delete_gcs_file, make_api_request, parse_date, format_bytes, update_data_source_sync_status

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])

# Metrics tracking
total_api_calls = 0
script_start_time = time.time()

# Load environment variables
USER_ID = ""
GCS_BUCKET_NAME = ""
MAX_WORKERS = int(os.environ.get('MAX_WORKERS', '4'))  # Parallel processing workers

# Slack API endpoints
SLACK_API_BASE = 'https://slack.com/api'

# Rate limiting constants
MAX_RETRIES = 5
BASE_DELAY = 1  # Base delay in seconds
MAX_DELAY = 300  # Maximum delay in seconds

def safe_parse_date(timestamp):
    """Safely parse various timestamp formats from Slack"""
    if not timestamp:
        return None
    
    try:
        # Handle string timestamps
        if isinstance(timestamp, str):
            # Try to convert to float first
            try:
                timestamp = float(timestamp)
            except ValueError:
                # If it's already an ISO format string, try parsing directly
                try:
                    return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                except ValueError:
                    return None
        
        # Handle numeric timestamps (Unix timestamps)
        if isinstance(timestamp, (int, float)):
            # Make timezone-aware by assuming UTC
            from datetime import timezone
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        
        return None
    except Exception as e:
        log.warning(f"Failed to parse timestamp {timestamp}: {str(e)}")
        return None

def make_request_with_retry(url, method='GET', headers=None, params=None, data=None, stream=False, auth_token=None):
    """Helper function to make API requests with retry logic for rate limiting"""
    global total_api_calls
    
    # Track rate limit info across attempts
    last_rate_limit_reset = None
    last_remaining_requests = None
    
    for attempt in range(MAX_RETRIES):
        total_api_calls += 1
        
        try:
            response = make_api_request(url, method=method, headers=headers, params=params, data=data, stream=stream, auth_token=auth_token)
            
            # Extract and log rate limit headers if available
            if hasattr(response, 'headers'):
                remaining = response.headers.get('X-Rate-Limit-Remaining')
                reset_time = response.headers.get('X-Rate-Limit-Reset')
                limit = response.headers.get('X-Rate-Limit-Limit')
                
                if remaining and reset_time:
                    last_remaining_requests = int(remaining)
                    last_rate_limit_reset = int(reset_time)
                    
                    # Log rate limit status
                    if int(remaining) < 5:
                        print(f"Warning: Only {remaining}/{limit} requests remaining until {time.ctime(int(reset_time))}")
            
            # Check if response is a dict (JSON response) and has rate limit error
            if isinstance(response, dict) and not response.get('ok') and response.get('error') == 'ratelimited':
                if attempt < MAX_RETRIES - 1:
                    delay = calculate_delay(attempt, last_rate_limit_reset)
                    print(f"Slack API rate limited, waiting {delay:.2f}s before retry {attempt + 1}/{MAX_RETRIES}")
                    time.sleep(delay)
                    continue
                else:
                    raise Exception(f"Slack API rate limited after {MAX_RETRIES} attempts")
            
            # Check if it's an HTTP response object with status code 429
            if hasattr(response, 'status_code') and response.status_code == 429:
                if attempt < MAX_RETRIES - 1:
                    # Prioritize Retry-After header, then rate limit reset time, then exponential backoff
                    delay = get_optimal_delay(response, attempt, last_rate_limit_reset)
                    print(f"HTTP 429 rate limited, waiting {delay:.2f}s before retry {attempt + 1}/{MAX_RETRIES}")
                    time.sleep(delay)
                    continue
                else:
                    raise Exception(f"HTTP 429 rate limited after {MAX_RETRIES} attempts")
            
            # Success - check if we should proactively slow down
            if last_remaining_requests is not None and last_remaining_requests < 3:
                # Proactively slow down to avoid hitting limits
                proactive_delay = calculate_proactive_delay(last_remaining_requests, last_rate_limit_reset)
                if proactive_delay > 0:
                    print(f"Proactively waiting {proactive_delay:.2f}s to avoid rate limits ({last_remaining_requests} requests remaining)")
                    time.sleep(proactive_delay)
            
            return response
            
        except Exception as e:
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in ["429", "rate", "too many requests", "ratelimited"]):
                if attempt < MAX_RETRIES - 1:
                    delay = calculate_delay(attempt, last_rate_limit_reset)
                    print(f"Rate limit error detected: {str(e)}")
                    print(f"Waiting {delay:.2f}s before retry {attempt + 1}/{MAX_RETRIES}")
                    time.sleep(delay)
                    continue
                else:
                    raise Exception(f"Rate limited after {MAX_RETRIES} attempts: {str(e)}")
            else:
                # For non-rate-limit errors, don't retry
                raise
    
    raise Exception(f"Failed after {MAX_RETRIES} attempts")

def get_optimal_delay(response, attempt, last_rate_limit_reset=None):
    """Calculate optimal delay based on available information"""
    
    # 1. Check for Retry-After header (most authoritative)
    retry_after = response.headers.get('Retry-After')
    if retry_after:
        delay = min(int(retry_after), MAX_DELAY)
        print(f"Using Retry-After header: {delay}s")
        return delay
    
    # 2. Check for rate limit reset time
    reset_time = response.headers.get('X-Rate-Limit-Reset')
    if reset_time:
        current_time = time.time()
        reset_delay = int(reset_time) - current_time
        if reset_delay > 0:
            delay = min(reset_delay + random.uniform(0.5, 2.0), MAX_DELAY)  # Add small buffer
            print(f"Using rate limit reset time: {delay:.2f}s")
            return delay
    
    # 3. Fall back to exponential backoff with jitter
    delay = calculate_delay(attempt, last_rate_limit_reset)
    print(f"Using exponential backoff: {delay:.2f}s")
    return delay

def calculate_delay(attempt, last_rate_limit_reset=None):
    """Calculate delay using exponential backoff with jitter"""
    
    # If we know when the rate limit resets, factor that in
    if last_rate_limit_reset:
        current_time = time.time()
        reset_delay = last_rate_limit_reset - current_time
        if reset_delay > 0 and reset_delay < MAX_DELAY:
            # If reset is soon, wait for it plus small buffer
            return min(reset_delay + random.uniform(0.5, 2.0), MAX_DELAY)
    
    # Standard exponential backoff with jitter
    base_delay = BASE_DELAY * (2 ** attempt)
    jitter = random.uniform(0, min(base_delay * 0.1, 2.0))  # 10% jitter, max 2s
    return min(base_delay + jitter, MAX_DELAY)

def calculate_proactive_delay(remaining_requests, reset_time):
    """Calculate proactive delay to avoid hitting rate limits"""
    if not reset_time or remaining_requests >= 3:
        return 0
    
    current_time = time.time()
    time_until_reset = reset_time - current_time
    
    if time_until_reset <= 0:
        return 0
    
    # Distribute remaining requests evenly over time until reset
    if remaining_requests > 0:
        optimal_interval = time_until_reset / remaining_requests
        # Only delay if we're going too fast
        return max(0, optimal_interval - 1.0)  # Leave 1s buffer
    
    return time_until_reset

def make_request(url, method='GET', headers=None, params=None, data=None, stream=False, auth_token=None):
    """Helper function to make API requests with error handling"""
    return make_request_with_retry(url, method=method, headers=headers, params=params, data=data, stream=stream, auth_token=auth_token)

def get_slack_user_info(auth_token):
    """Get information about the authenticated user"""
    try:
        url = f"{SLACK_API_BASE}/auth.test"
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = make_request(url, headers=headers, auth_token=auth_token)

        log.info(f"Slack user info response: {response}")
        
        if response.get('ok'):
            return {
                'user_id': response.get('user_id'),
                'user': response.get('user'),
                'team': response.get('team'),
                'team_id': response.get('team_id')
            }
        else:
            raise Exception(f"Failed to get user info: {response.get('error')}")
            
    except Exception as error:
        print(f"Error getting user info: {str(error)}")
        return None

def check_user_membership(conversation_id, auth_token, target_user_id):
    """Check if the target user is a member of the channel"""
    try:
        url = f"{SLACK_API_BASE}/conversations.members"
        headers = {"Authorization": f"Bearer {auth_token}"}
        params = {
            'channel': conversation_id,
            'limit': 1000
        }
        
        cursor = None
        while True:
            if cursor:
                params['cursor'] = cursor
            
            response = make_request(url, headers=headers, params=params, auth_token=auth_token)
            
            if response.get('ok'):
                members = response.get('members', [])
                if target_user_id in members:
                    return True
                
                # Check for pagination
                cursor = response.get('response_metadata', {}).get('next_cursor')
                if not cursor:
                    break
            else:
                # If we can't check membership, assume they're not a member
                return False
        
        return False
            
    except Exception as error:
        print(f"Error checking membership for {conversation_id}: {str(error)}")
        return False

def check_user_is_member(conversation_id, auth_token):
    """Check if the authenticated user is a member of the conversation"""
    try:
        url = f"{SLACK_API_BASE}/conversations.info"
        headers = {"Authorization": f"Bearer {auth_token}"}
        params = {'channel': conversation_id}
        
        response = make_request(url, headers=headers, params=params, auth_token=auth_token)
        
        if response.get('ok'):
            channel_info = response.get('channel', {})
            # User is a member if they can access channel info and is_member is True
            return channel_info.get('is_member', False)
        else:
            # If we can't get channel info, assume we're not a member
            return False
            
    except Exception as error:
        print(f"Error checking membership for {conversation_id}: {str(error)}")
        return False

def join_channel_if_user_is_member(conversation_id, auth_token, target_user_id, conversation_name=""):
    """Join a channel only if the target user is already a member"""
    try:
        # First check if the target user is a member
        user_is_member = check_user_membership(conversation_id, auth_token, target_user_id)
        
        if not user_is_member:
            print(f"⚠️  Target user not a member of {conversation_name} ({conversation_id}), skipping join attempt")
            return False
        
        print(f"🔗 Target user is member of {conversation_name}, attempting to join...")
        
        url = f"{SLACK_API_BASE}/conversations.join"
        headers = {"Authorization": f"Bearer {auth_token}"}
        params = {'channel': conversation_id}
        
        response = make_request(url, method='POST', headers=headers, params=params, auth_token=auth_token)
        
        if response.get('ok'):
            print(f"✅ Successfully joined {conversation_name}")
            return True
        else:
            error_msg = response.get('error', 'unknown_error')
            print(f"❌ Failed to join {conversation_name}: {error_msg}")
            return False
        
    except Exception as error:
        print(f"Error joining channel {conversation_id}: {str(error)}")
        return False

def get_conversations_list(auth_token, types="public_channel,private_channel,mpim,im"):
    """Get list of conversations the user has access to and is a member of"""
    try:
        all_conversations = []
        cursor = None
        
        while True:
            params = {
                'types': types,
                'exclude_archived': 'false',
                'limit': 1000
            }
            
            if cursor:
                params['cursor'] = cursor
            
            url = f"{SLACK_API_BASE}/conversations.list"
            headers = {"Authorization": f"Bearer {auth_token}"}
            
            response = make_request(url, headers=headers, params=params, auth_token=auth_token)
            
            if not response.get('ok'):
                raise Exception(f"Failed to get conversations: {response.get('error')}")
            
            conversations = response.get('channels', [])
            
            # Filter conversations to only include those where user is a member
            for conv in conversations:
                # For DMs (im) and group DMs (mpim), user is always a member if they're in the list
                if conv.get('is_im') or conv.get('is_mpim'):
                    all_conversations.append(conv)
                # For channels, check if user is a member
                elif conv.get('is_member', False):
                    all_conversations.append(conv)
                # For channels where is_member is not reliable, do an explicit check
                elif check_user_is_member(conv['id'], auth_token):
                    all_conversations.append(conv)
            
            # Check for pagination
            cursor = response.get('response_metadata', {}).get('next_cursor')
            if not cursor:
                break
        
        return all_conversations
        
    except Exception as error:
        print(f"Error getting conversations: {str(error)}")
        return []
    
def download_existing_conversation_from_gcs(conversation_path, service_account_base64, gcs_bucket_name):
    """Download existing conversation data from GCS"""
    try:
        # This function needs to be implemented - it should download the JSON file from GCS
        # and return the parsed conversation data
        file_content = download_from_gcs(conversation_path, service_account_base64, gcs_bucket_name)
        if file_content:
            return json.loads(file_content.decode('utf-8'))
        return None
    except Exception as error:
        print(f"Error downloading existing conversation from GCS: {str(error)}")
        return None

def get_conversation_history_incremental(conversation_id, auth_token, conversation_name="", last_message_ts=None):
    """Get message history for a conversation, optionally from a specific timestamp"""
    try:
        all_messages = []
        cursor = None
        
        while True:
            params = {
                'channel': conversation_id,
                'limit': 1000,
                'inclusive': 'true'
            }
            
            # If we have a last message timestamp, only fetch messages after it
            if last_message_ts:
                params['oldest'] = str(float(last_message_ts) + 0.000001)  # Add tiny increment to exclude the last message
            
            if cursor:
                params['cursor'] = cursor
            
            url = f"{SLACK_API_BASE}/conversations.history"
            headers = {"Authorization": f"Bearer {auth_token}"}
            
            response = make_request(url, headers=headers, params=params, auth_token=auth_token)
            
            if not response.get('ok'):
                error_msg = response.get('error', 'unknown_error')
                print(f"⚠️  Failed to get history for {conversation_name} ({conversation_id}): {error_msg}")
                return []
            
            messages = response.get('messages', [])
            all_messages.extend(messages)
            
            # Check for pagination
            cursor = response.get('response_metadata', {}).get('next_cursor')
            if not cursor:
                break
            
            # Add delay between requests
            if cursor:  # Only sleep if there are more pages
                print(f"Waiting 30s before fetching next batch for {conversation_name}...")
                time.sleep(30)
        
        return all_messages
        
    except Exception as error:
        print(f"Error getting conversation history for {conversation_id}: {str(error)}")
        return []
    
def merge_conversation_messages(existing_messages, new_messages):
    """Merge existing and new messages, handling updates and deletions"""
    try:
        # Create a map of existing messages by timestamp for quick lookup
        existing_msg_map = {msg.get('ts'): msg for msg in existing_messages if msg.get('ts')}
        
        # Start with existing messages
        all_messages = list(existing_messages)
        
        # Process new messages
        for new_msg in new_messages:
            msg_ts = new_msg.get('ts')
            if not msg_ts:
                continue
                
            # If message already exists, update it (handles edits)
            if msg_ts in existing_msg_map:
                # Find and replace the existing message
                for i, existing_msg in enumerate(all_messages):
                    if existing_msg.get('ts') == msg_ts:
                        all_messages[i] = new_msg
                        break
            else:
                # Add new message
                all_messages.append(new_msg)
        
        # Sort messages by timestamp
        all_messages.sort(key=lambda x: float(x.get('ts', 0)))
        
        # Handle deleted messages - this is tricky because Slack doesn't explicitly tell us
        # about deletions in the API. For now, we'll keep all messages we have.
        # A more sophisticated approach would be to periodically do a full sync
        # to catch deletions, or implement a separate deletion detection mechanism.
        
        return all_messages
        
    except Exception as error:
        print(f"Error merging conversation messages: {str(error)}")
        return existing_messages
    
def get_latest_message_timestamp(messages):
    """Get the timestamp of the most recent message"""
    if not messages:
        return None
    
    try:
        # Sort messages by timestamp and get the latest
        sorted_messages = sorted(messages, key=lambda x: float(x.get('ts', 0)), reverse=True)
        return sorted_messages[0].get('ts') if sorted_messages else None
    except Exception as error:
        print(f"Error getting latest message timestamp: {str(error)}")
        return None
    
def check_file_exists_in_gcs(file_id, service_account_base64, gcs_bucket_name):
    """Check if a file with the given Slack file ID already exists in GCS"""
    try:
        # List all files in the user's Slack files directory
        user_prefix = f"userResources/{USER_ID}/Slack/Files/"
        gcs_files = list_gcs_files(service_account_base64, gcs_bucket_name, prefix=user_prefix)
        
        # Check if any file has this file ID in its metadata or path
        for gcs_file in gcs_files:
            # We'll need to store the Slack file ID in the file path or metadata
            # For now, let's assume we include it in the filename
            if f"_{file_id}" in gcs_file['name'] or gcs_file['name'].endswith(f"_{file_id}"):
                return gcs_file
        
        return None
        
    except Exception as error:
        print(f"Error checking if file exists in GCS: {str(error)}")
        return None

def get_user_direct_messages(auth_token, user_id):
    """Get all direct message conversations for the user"""
    try:
        # Get IM conversations specifically
        url = f"{SLACK_API_BASE}/conversations.list"
        headers = {"Authorization": f"Bearer {auth_token}"}
        params = {
            'types': 'im',
            'exclude_archived': 'false',
            'limit': 1000
        }
        
        response = make_request(url, headers=headers, params=params, auth_token=auth_token)
        
        if response.get('ok'):
            return response.get('channels', [])
        else:
            print(f"Failed to get DMs: {response.get('error')}")
            return []
            
    except Exception as error:
        print(f"Error getting direct messages: {str(error)}")
        return []

def get_conversation_history(conversation_id, auth_token, conversation_name="", target_user_id=""):
    """Get message history for a specific conversation"""
    try:
        # ... existing code until the while loop ...
        
        all_messages = []
        cursor = None
        
        while True:
            params = {
                'channel': conversation_id,
                'limit': 1000,
                'inclusive': 'true'
            }
            
            if cursor:
                params['cursor'] = cursor
            
            url = f"{SLACK_API_BASE}/conversations.history"
            headers = {"Authorization": f"Bearer {auth_token}"}
            
            response = make_request(url, headers=headers, params=params, auth_token=auth_token)
            
            if not response.get('ok'):
                error_msg = response.get('error', 'unknown_error')
                print(f"⚠️  Failed to get history for {conversation_name} ({conversation_id}): {error_msg}")
                return []
            
            messages = response.get('messages', [])
            all_messages.extend(messages)
            
            # Check for pagination
            cursor = response.get('response_metadata', {}).get('next_cursor')
            if not cursor:
                break
            
            # Add 30-second delay before next fetch
            print(f"Waiting 30s before fetching next batch for {conversation_name}...")
            time.sleep(30)
        
        return all_messages
        
    except Exception as error:
        print(f"Error getting conversation history for {conversation_id}: {str(error)}")
        return []

def get_conversation_replies(conversation_id, thread_ts, auth_token):
    """Get replies for a specific thread"""
    try:
        params = {
            'channel': conversation_id,
            'ts': thread_ts,
            'limit': 1000
        }
        
        url = f"{SLACK_API_BASE}/conversations.replies"
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = make_request(url, headers=headers, params=params, auth_token=auth_token)
        
        if response.get('ok'):
            return response.get('messages', [])
        else:
            return []
            
    except Exception as error:
        print(f"Error getting thread replies: {str(error)}")
        return []

def get_user_info_batch(auth_token, user_ids):
    """Get user information for multiple users"""
    try:
        user_info_map = {}
        
        # Slack API allows up to 50 users per call for users.info
        for i in range(0, len(user_ids), 50):
            batch_ids = user_ids[i:i+50]
            
            for user_id in batch_ids:
                try:
                    url = f"{SLACK_API_BASE}/users.info"
                    headers = {"Authorization": f"Bearer {auth_token}"}
                    params = {'user': user_id}
                    
                    response = make_request(url, headers=headers, params=params, auth_token=auth_token)
                    
                    if response.get('ok'):
                        user_info = response.get('user', {})
                        user_info_map[user_id] = user_info.get('name', user_id)
                    else:
                        user_info_map[user_id] = user_id
                        
                except Exception as e:
                    user_info_map[user_id] = user_id
        
        return user_info_map
        
    except Exception as error:
        print(f"Error getting user info batch: {str(error)}")
        return {}

def get_user_files(auth_token, user_id):
    """Get files uploaded by the user"""
    try:
        all_files = []
        page = 1
        
        while True:
            params = {
                'user': user_id,
                'count': 1000,
                'page': page
            }
            
            url = f"{SLACK_API_BASE}/files.list"
            headers = {"Authorization": f"Bearer {auth_token}"}
            
            response = make_request(url, headers=headers, params=params, auth_token=auth_token)
            
            if not response.get('ok'):
                print(f"Failed to get files: {response.get('error')}")
                break
            
            files = response.get('files', [])
            if not files:
                break
                
            all_files.extend(files)
            
            # Check if we have more pages
            paging = response.get('paging', {})
            if page >= paging.get('pages', 1):
                break
                
            page += 1
        
        return all_files
        
    except Exception as error:
        print(f"Error getting user files: {str(error)}")
        return []

def download_slack_file(file_info, auth_token):
    """Download a file from Slack"""
    try:
        file_url = file_info.get('url_private_download') or file_info.get('url_private')
        if not file_url:
            raise Exception("No download URL available")
        
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        with make_request(file_url, headers=headers, stream=True, auth_token=auth_token) as response:
            # make_request (which internally calls make_api_request) already calls response.raise_for_status()
            # If make_api_request is robust, this check might be redundant but doesn't hurt.
            # response.raise_for_status() 
            
            file_content = io.BytesIO()
            for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                if chunk:
                    file_content.write(chunk)
        
        file_content.seek(0)
        return file_content
        
    except Exception as error:
        print(f"Error downloading file {file_info.get('name', 'unknown')}: {str(error)}")
        # For a production application, use `log.error(..., exc_info=True)` here
        # log.error(f"Error downloading file {file_info.get('name', 'unknown')}:", exc_info=True)
        return None # Return None as stated in the original function's error path

def process_conversation(conversation, auth_token, slack_user_id, user_info_map, service_account_base64, gcs_bucket_name):
    """Process a single conversation with incremental updates"""
    try:
        conversation_id = conversation['id']
        conversation_name = conversation.get('name', conversation_id)
        conversation_type = 'dm' if conversation.get('is_im') else 'channel'
        
        print(f"Processing {conversation_type}: {conversation_name}")
        
        # Create file path based on conversation type and name
        if conversation.get('is_im'):
            other_user = conversation.get('user', 'unknown_user')
            other_user_name = user_info_map.get(other_user, other_user)
            file_path = f"userResources/{USER_ID}/Slack/Direct Messages/{other_user_name}.json"
        elif conversation.get('is_mpim'):
            file_path = f"userResources/{USER_ID}/Slack/Group Messages/{conversation_name}.json"
        else:
            file_path = f"userResources/{USER_ID}/Slack/Channels/{conversation_name}.json"
        
        # Check if conversation already exists in GCS
        existing_conversation_data = download_existing_conversation_from_gcs(
            file_path, service_account_base64, gcs_bucket_name
        )
        
        existing_messages = []
        last_message_ts = None
        
        if existing_conversation_data:
            print(f"📥 Found existing conversation data for {conversation_name}")
            existing_messages = existing_conversation_data.get('messages', [])
            last_message_ts = get_latest_message_timestamp(existing_messages)
            
            if last_message_ts:
                print(f"🕐 Last message timestamp: {last_message_ts}")
        
        # Get new messages (or all messages if no existing data)
        new_messages = get_conversation_history_incremental(
            conversation_id, auth_token, conversation_name, last_message_ts
        )
        
        if not new_messages and not existing_messages:
            print(f"⚠️  No messages found for {conversation_name}, skipping...")
            return None
        
        # Merge existing and new messages
        if existing_messages:
            all_messages = merge_conversation_messages(existing_messages, new_messages)
            print(f"📊 Merged {len(existing_messages)} existing + {len(new_messages)} new = {len(all_messages)} total messages")
        else:
            all_messages = new_messages
            print(f"📊 Found {len(all_messages)} messages in new conversation")
        
        # Get thread replies for messages that have them
        for message in all_messages:
            if message.get('thread_ts') and message.get('reply_count', 0) > 0:
                # Only fetch replies if we don't already have them or if this is a new message
                if not message.get('replies') or message in new_messages:
                    replies = get_conversation_replies(conversation_id, message['thread_ts'], auth_token)
                    message['replies'] = replies
        
        # Create conversation data structure
        conversation_data = {
            'conversation_info': conversation,
            'messages': all_messages,
            'exported_at': datetime.now(timezone.utc).isoformat(),
            'total_messages': len(all_messages),
            'last_sync_timestamp': last_message_ts,
            'incremental_sync': existing_conversation_data is not None
        }
        
        # Get the most recent message timestamp for comparison
        message_dates = []
        for msg in all_messages:
            if msg.get('ts'):
                parsed_date = safe_parse_date(msg.get('ts'))
                if parsed_date:
                    message_dates.append(parsed_date)
        
        modified_time = max(message_dates) if message_dates else datetime.now(timezone.utc)
        
        return {
            'path': file_path,
            'data': conversation_data,
            'size': len(json.dumps(conversation_data).encode('utf-8')),
            'modified_time': modified_time,
            'is_update': existing_conversation_data is not None,
            'new_messages_count': len(new_messages)
        }
        
    except Exception as error:
        print(f"Error processing conversation {conversation.get('name', conversation.get('id'))}: {str(error)}")
        return None

def process_file(file_info, auth_token, service_account_base64, gcs_bucket_name):
    """Process a single file, skipping if already exists in GCS"""
    try:
        file_id = file_info['id']
        file_name = file_info.get('name', f"file_{file_id}")
        file_size = file_info.get('size', 0)
        
        print(f"Processing file: {file_name} ({format_bytes(file_size)})")
        
        # Check if file already exists in GCS
        existing_gcs_file = check_file_exists_in_gcs(file_id, service_account_base64, gcs_bucket_name)
        
        if existing_gcs_file:
            print(f"⏭️  File {file_name} already exists in GCS, skipping...")
            return {
                'skipped': True,
                'path': existing_gcs_file['name'],
                'reason': 'Already exists in GCS'
            }
        
        # Download file content
        file_content = download_slack_file(file_info, auth_token)
        if not file_content:
            return None
        
        # Create file path with file ID to ensure uniqueness
        safe_filename = f"{file_name}_{file_id}"
        file_path = f"userResources/{USER_ID}/Slack/Files/{safe_filename}"
        
        # Use safe_parse_date for file timestamp
        file_timestamp = file_info.get('timestamp')
        modified_time = safe_parse_date(file_timestamp) if file_timestamp else datetime.now(timezone.utc)
        
        return {
            'path': file_path,
            'content': file_content,
            'size': file_size,
            'mime_type': file_info.get('mimetype'),
            'modified_time': modified_time,
            'file_id': file_id,
            'skipped': False
        }
        
    except Exception as error:
        print(f"Error processing file {file_info.get('name', 'unknown')}: {str(error)}")
        return None

def upload_conversation_to_gcs(conversation_data, service_account_base64, gcs_bucket_name):
    """Upload conversation JSON to GCS"""
    try:
        json_content = json.dumps(conversation_data['data'], indent=2, default=str)
        json_bytes = io.BytesIO(json_content.encode('utf-8'))
        
        result = upload_to_gcs(
            json_bytes,
            conversation_data['path'],
            'application/json',
            service_account_base64,
            gcs_bucket_name
        )
        
        return result
        
    except Exception as error:
        print(f"Error uploading conversation {conversation_data['path']}: {str(error)}")
        return None

def upload_file_to_gcs(file_data, service_account_base64, gcs_bucket_name):
    """Upload file to GCS"""
    try:
        result = upload_to_gcs(
            file_data['content'],
            file_data['path'],
            file_data['mime_type'],
            service_account_base64,
            gcs_bucket_name
        )
        
        return result
        
    except Exception as error:
        print(f"Error uploading file {file_data['path']}: {str(error)}")
        return None

async def sync_slack_to_gcs(auth_token, service_account_base64):
    """Main function to sync Slack data to Google Cloud Storage with incremental updates"""
    global total_api_calls
    global GCS_BUCKET_NAME
    
    print('🔄 Starting Slack sync process...')
    
    uploaded_files = []
    deleted_files = []
    skipped_files = 0
    
    try:
        # Get user info
        user_info = get_slack_user_info(auth_token)
        if not user_info:
            raise ValueError("Could not retrieve user information")
        
        slack_user_id = user_info['user_id']
        print(f"Syncing data for user: {user_info['user']} ({slack_user_id})")
        
        # Get conversations where user is a member
        print("Fetching conversations where user is a member...")
        conversations = get_conversations_list(auth_token)
        
        # Also explicitly fetch DMs
        print("Fetching direct messages...")
        direct_messages = get_user_direct_messages(auth_token, slack_user_id)
        
        # Combine and deduplicate conversations
        all_conversations = conversations + direct_messages
        seen_ids = set()
        unique_conversations = []
        
        for conv in all_conversations:
            if conv['id'] not in seen_ids:
                unique_conversations.append(conv)
                seen_ids.add(conv['id'])
        
        print(f"Found {len(unique_conversations)} total conversations ({len(direct_messages)} DMs)")
        
        # Get user info for DM naming
        print("Fetching user information for DM naming...")
        dm_user_ids = [conv.get('user') for conv in unique_conversations if conv.get('is_im') and conv.get('user')]
        user_info_map = get_user_info_batch(auth_token, dm_user_ids) if dm_user_ids else {}
        
        # Get user files
        print("Fetching files...")
        files = get_user_files(auth_token, slack_user_id)
        print(f"Found {len(files)} files")
        
        # Process conversations with incremental updates
        print("\nProcessing conversations...")
        conversation_paths = set()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit conversation processing tasks
            conv_futures = {
                executor.submit(
                    process_conversation, 
                    conv, 
                    auth_token, 
                    slack_user_id, 
                    user_info_map,
                    service_account_base64,
                    GCS_BUCKET_NAME
                ): conv
                for conv in unique_conversations
            }
            
            # Process completed conversation tasks
            for future in concurrent.futures.as_completed(conv_futures):
                try:
                    conv_data = future.result()
                    if conv_data:
                        conversation_paths.add(conv_data['path'])
                        
                        # Always upload conversations (they handle their own incremental logic)
                        start_time = time.time()
                        result = upload_conversation_to_gcs(conv_data, service_account_base64, GCS_BUCKET_NAME)
                        
                        if result:
                            uploaded_files.append({
                                'path': conv_data['path'],
                                'type': 'updated' if conv_data['is_update'] else 'new',
                                'size': conv_data['size'],
                                'durationMs': int((time.time() - start_time) * 1000),
                                'reason': f"{'Incremental update' if conv_data['is_update'] else 'New conversation'} - {conv_data['new_messages_count']} new messages"
                            })
                            print(f"[{datetime.now().isoformat()}] {'Updated' if conv_data['is_update'] else 'Uploaded'} {conv_data['path']}")
                            
                except Exception as e:
                    conv = conv_futures[future]
                    print(f"Error processing conversation {conv.get('name', conv.get('id'))}: {str(e)}")
        
        # Process files with existence checking
        print("\nProcessing files...")
        file_paths = set()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit file processing tasks
            file_futures = {
                executor.submit(
                    process_file, 
                    file_info, 
                    auth_token,
                    service_account_base64,
                    GCS_BUCKET_NAME
                ): file_info
                for file_info in files
            }
            
            # Process completed file tasks
            for future in concurrent.futures.as_completed(file_futures):
                try:
                    file_data = future.result()
                    if file_data:
                        if file_data.get('skipped'):
                            skipped_files += 1
                            file_paths.add(file_data['path'])
                        else:
                            file_paths.add(file_data['path'])
                            
                            start_time = time.time()
                            result = upload_file_to_gcs(file_data, service_account_base64, GCS_BUCKET_NAME)
                            
                            if result:
                                uploaded_files.append({
                                    'path': file_data['path'],
                                    'type': 'new',
                                    'size': file_data['size'],
                                    'durationMs': int((time.time() - start_time) * 1000),
                                    'reason': 'New file'
                                })
                                print(f"[{datetime.now().isoformat()}] Uploaded {file_data['path']}")
                            
                except Exception as e:
                    file_info = file_futures[future]
                    print(f"Error processing file {file_info.get('name', 'unknown')}: {str(e)}")
        
        # Clean up orphaned files (same as before)
        gcs_files = list_gcs_files(service_account_base64, GCS_BUCKET_NAME)
        gcs_file_map = {gcs_file['name']: gcs_file for gcs_file in gcs_files}
        
        user_prefix = f"userResources/{USER_ID}/Slack/"
        all_current_paths = conversation_paths | file_paths
        
        for gcs_name, gcs_file in gcs_file_map.items():
            if gcs_name.startswith(user_prefix) and gcs_name not in all_current_paths:
                delete_gcs_file(gcs_name, service_account_base64, GCS_BUCKET_NAME)
                
                deleted_files.append({
                    'name': gcs_name,
                    'size': gcs_file.get('size'),
                    'timeCreated': gcs_file.get('timeCreated')
                })
                print(f"[{datetime.now().isoformat()}] Deleted orphan: {gcs_name}")
        
        # Enhanced summary
        print('\nSync Summary:')
        for file in uploaded_files:
            symbol = '+' if file['type'] == 'new' else '^'
            print(
                f" {symbol} {file['path']} | {format_bytes(file['size'])} | {file['durationMs']}ms | {file['reason']}"
            )
        
        for file in deleted_files:
            print(f" - {file['name']} | {format_bytes(file['size'])} | Created: {file['timeCreated']}")
        
        total_runtime = int((time.time() - script_start_time) * 1000)

        await update_data_source_sync_status(USER_ID, 'slack', 'synced')

        print("\nAccounting Metrics:")
        print(f"⏱️  Total Runtime: {(total_runtime/1000):.2f} seconds")
        print(f"📊 Billable API Calls: {total_api_calls}")
        print(f"💬 Conversations Processed: {len(unique_conversations)}")
        print(f"📁 Files Processed: {len(files)}")
        print(f"🗑️  Orphans Removed: {len(deleted_files)}")
        print(f"⏭️  Files Skipped (already exist): {skipped_files}")
        
        print(f"\nTotal: +{len([f for f in uploaded_files if f['type'] == 'new'])} added, " +
              f"^{len([f for f in uploaded_files if f['type'] == 'updated'])} updated, " +
              f"-{len(deleted_files)} removed, {skipped_files} skipped")
    
    except Exception as error:
        await update_data_source_sync_status(USER_ID, 'slack', 'error')
        print(f'Slack Sync failed: {str(error)}')
        print(f"[{datetime.now().isoformat()}] Sync failed critically: {str(error)}")
        print(traceback.format_exc())
        raise

# Main Execution Function
async def initiate_slack_sync(user_id: str, token: str, creds: str, gcs_bucket_name: str):
    """
    Main execution function for Slack to GCS sync
    
    Args:
        user_id (str): User ID from your app
        token (str): Slack OAuth token
        creds (str): Base64 encoded GCS service account credentials
        gcs_bucket_name (str): Name of the GCS bucket
    """
    log.info(f'Sync Slack to Google Cloud Storage')
    log.info(f'User Open WebUI ID: {user_id}')
    log.info(f'GCS Bucket Name: {gcs_bucket_name}')

    global USER_ID 
    global GCS_BUCKET_NAME
    global script_start_time
    global total_api_calls

    USER_ID = user_id
    GCS_BUCKET_NAME = gcs_bucket_name
    total_api_calls = 0
    script_start_time = time.time()

    # Validate token quickly before starting async process
    user_info = get_slack_user_info(token)
    if not user_info:
        raise ValueError("Invalid Slack token or could not retrieve user information")

    await sync_slack_to_gcs(token, creds)
    
    # Return immediate response
    return {
        "status": "started",
        "message": "Slack sync process has been initiated successfully",
        "user_id": user_id,
        "slack_user": user_info.get('user', 'unknown')
    }