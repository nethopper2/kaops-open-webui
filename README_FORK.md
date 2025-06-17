# Summary of changes on this fork

## ENV vars

### 0.6.5
* **NH_API_BASE_URL** - The base of the url for the private-ai-rest dependency.
* **NH_ENABLE_UPSTREAM_UI** - When `true`, UI behaves as it does without our modification. When `false` or not defined, this affects:
    * The update available Toast notification is not shown.
    * The settings UI for checking for an update and toggling the update Toast Notification is not shown. This can be verified by:
        * Clicking the lower left user, then `Settings`. Under `Interface` you should not see `Toast notifications for new updates`.
        * Clicking the lower left user, then `Settings`. Under `About` you should not see any buttons or text about an upgrade or checking for an upgrade, only the version string.
        * Clicking the lower left user, then `Admin Panel`. Under `Settings/General` you should not see any buttons or text about an upgrade or checking for an upgrade, only the version string. (NOTE: Do we need this info in 2 places?)
      * Social Links in the `Settings/Interface` area mentioned above.
      * License link & Social Links in the `Admin Panel` area mentioned above.
    * The api call to `api/version/updates` is not made in the above areas.
    * Hid the `her` theme in `Settings/General` since it made unexplained changes to the UI.
    * Replaced the `Workspace/Knowledge` section with our own component for use with Google Drive & RAG.
    * Hid the `Discover a ...` button in each of the subsections in `Workspace` since they link to nothing useful.

## Branding

### 0.5.x
Here is a list of custom WebUI branding assets. **Eventually** we want our post install job to overwrite the default assets with the corresponding images stored in S3.
- static/assets/images/bridge.jpg              <-- https://nh-addon-themes.s3.us-east-1.amazonaws.com/private-ai/images/bridge.jpg
- static/assets/images/chess.jpg               <-- https://nh-addon-themes.s3.us-east-1.amazonaws.com/private-ai/images/chess.jpg
- static/assets/images/climber.jpg             <-- https://nh-addon-themes.s3.us-east-1.amazonaws.com/private-ai/images/climber.jpg
- static/assets/images/lock.jpg                <-- https://nh-addon-themes.s3.us-east-1.amazonaws.com/private-ai/images/lock.jpg
- static/favicon.png (96px x 96px)             <-- https://nh-addon-themes.s3.us-east-1.amazonaws.com/private-ai/favicon.png
- static/static/apple-touch-icon.png           <-- https://nh-addon-themes.s3.us-east-1.amazonaws.com/private-ai/apple-touch-icon.png
- static/static/favicon-96x96.png              <-- https://nh-addon-themes.s3.us-east-1.amazonaws.com/private-ai/favicon-96x96.png
- static/static/favicon-dark.png               <-- https://nh-addon-themes.s3.us-east-1.amazonaws.com/private-ai/favicon-dark.png
- static/static/favicon.ico                    <-- https://nh-addon-themes.s3.us-east-1.amazonaws.com/private-ai/favicon.ico
- static/static/favicon.png                    <-- https://nh-addon-themes.s3.us-east-1.amazonaws.com/private-ai/favicon.png
- static/static/favicon.svg                    <-- https://nh-addon-themes.s3.us-east-1.amazonaws.com/private-ai/favicon.svg
- static/static/ollama.png                     <-- https://nh-addon-themes.s3.us-east-1.amazonaws.com/private-ai/ollama.png
- static/static/splash-dark.png                <-- https://nh-addon-themes.s3.us-east-1.amazonaws.com/private-ai/splash-dark.png
- static/static/splash.png                     <-- https://nh-addon-themes.s3.us-east-1.amazonaws.com/private-ai/splash.png
- static/static/web-app-manifest-192x192.png   <-- https://nh-addon-themes.s3.us-east-1.amazonaws.com/private-ai/web-app-manifest-192x192.png
- static/static/web-app-manifest-512x512.png   <-- https://nh-addon-themes.s3.us-east-1.amazonaws.com/private-ai/web-app-manifest-512x512.png

## Suggestions component

### 0.5.x
We added a new suggestions component that has a similar look and feel to that of Chat GPT. Also
created new prompts that are more geared to a private corporate AI environment.

## LLM Selector

### 0.5.x
We made minor changes to the LLM selector, including
  - adding an Ollama icon next to the pull option
  - minor style changes to make the Ollama option stand out a little more than it does

## Onboarding

### 0.5.x
We replaced the background images and slogans to align more to a private corporate AI environment.
