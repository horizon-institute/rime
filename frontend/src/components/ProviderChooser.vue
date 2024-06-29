<!-- 
This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
See LICENSE.txt for full details.
Copyright 2023 Telemarq Ltd
-->
<script setup>
import { ref, computed } from 'vue';

import { rawEventsSearchResult } from '../store.js';

const allProviders = computed(() => {
  let providers = [];
  let seenProviders = {};

  if (rawEventsSearchResult.value) {
    for (let eventsForDevice of rawEventsSearchResult.value.events) {
      for (let provider of eventsForDevice.providers) {
        if (!seenProviders[provider.name]) {
          providers.push(provider);
          seenProviders[provider.name] = true;
        }
      }
    }
  }
  providers.sort((a, b) => a.friendlyName.localeCompare(b.friendlyName));
  return providers;
});
</script>

<template>
  <div id="view">
    <h1>Providers</h1>
    <div v-for="provider in allProviders" :key="provider" class="provider">
      <div class="providerFriendly">{{ provider.friendlyName }}</div>
      <div class="providerName">{{ provider.name }}</div>
    </div>
  </div>
</template>

<style scoped>
.provider {
  display: flex;
  flex-direction: column;
  border: 1px solid black;
}

.providerName {
  font-size: 0.8em;
}
</style>
