<script>
    import '../../../vue/register.ts'

    function handleCustomEvent(e) {
        alert(e.detail.message)
    }
</script>

<main>
<h1>Hello from Svelte</h1>
<my-vue-element on:custom-event={handleCustomEvent}></my-vue-element>
</main>