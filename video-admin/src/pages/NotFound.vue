<script setup lang="ts">
</script>

<template>
  <div class="flex flex-col items-center justify-center min-h-[50vh] text-center px-4">
    <h1 class="text-6xl font-bold text-muted-foreground/30">404</h1>
    <h2 class="mt-4 text-xl font-semibold">Oops!</h2>
    <p class="mt-2 text-muted-foreground">This page could not be found.</p>
    <RouterLink
      to="/"
      class="mt-6 inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90"
    >
      Go Back
    </RouterLink>
  </div>
</template>
