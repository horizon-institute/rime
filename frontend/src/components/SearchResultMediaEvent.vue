<!-- 
This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
See LICENSE.txt for full details.
Copyright 2023 Telemarq Ltd
-->
<script setup>
const props = defineProps({
  event: {
    type: Object,
    required: true,
  },
});

/* TODO: put this somewhere central; it's copy-pasted from SearchResultMessageEvent */
function formatEventTimestamp(event) {
  /* Show the full date and time if the time delta is null or greater than 24 hours, otherwise just the time. */
  const delta = event.previousTimestamp
    ? event.timestamp - event.previousTimestamp
    : null;

  if (
    event.previousTimestamp == null ||
    delta == null ||
    delta > 24 * 60 * 60 * 1000 ||
    event.previousTimestamp.getDate() != event.timestamp.getDate()
  ) {
    return (
      event.timestamp.toLocaleDateString() +
      ' ' +
      event.timestamp.toLocaleTimeString()
    );
  } else {
    return event.timestamp.toLocaleTimeString();
  }
}
</script>

<template>
  <div>
    <video v-if="event.mime_type.startsWith('video')" controls>
      <source :src="event.url" :type="event.media.mime_type" />
    </video>
    <img v-else :src="event.url" />
  </div>
</template>

<style scoped>
img {
  max-width: 100%;
}
</style>
