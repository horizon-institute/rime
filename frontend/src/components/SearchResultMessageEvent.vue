<!--
This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
See LICENSE.txt for full details.
Copyright 2023 Telemarq Ltd
-->
<template>
  <div>
    <div
      v-if="event.__typename == 'MessageEvent' && event.session !== null"
      class="sessioninfo"
    >
      {{ event.session.getParticipantsString(event) }}
    </div>
    <div
      class="message"
      v-if="event.__typename == 'MessageEvent'"
      :class="{ from_me: event.fromMe }"
    >
      <div class="message_body">
        <div v-if="event.media" class="message_media">
          <video v-if="event.media.mime_type.startsWith('video')" controls>
            <source :src="event.media.url" :type="event.media.mime_type" />
          </video>
          <img v-else :src="event.media.url" />
        </div>
        {{ event.text }}
      </div>
      <div class="metadata">
        <span
          class="sender"
          v-if="!event.fromMe && event.sender && !isPrivateChat(event)"
        >
          <span v-if="event.sender.name.display">{{
            event.sender.name.display
          }}</span>
          <span v-else-if="event.sender.name.first"
            >{{ event.sender.name.first }} {{ event.sender.name.last }}</span
          >
          <span v-if="event.sender.phone"> ({{ event.sender.phone }})</span>
          &nbsp;
        </span>
        <span class="timestamp"> {{ formatEventTimestamp(event) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  event: {
    type: Object,
    required: true,
  },
});

/* Is this MessageEvent a chat between the phone owner and a single other person? */
function isPrivateChat(event) {
  if (event.session == null) {
    return false;
  }

  return event.session.participants.length == 1;
}

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

<style scoped>
.MessageEvent {
  display: flex;
  flex-direction: column;
  align-items: start;
}

.MessageEvent > .from_me {
  align-self: flex-end;
}

.sessioninfo {
  font-size: 0.8em;
  margin: 0.5em;
  padding-left: 0;
  color: #444;
}

.message {
  margin: 0.5em;
  flex: 0;
  padding-left: 1em;
  display: flex;
  flex-direction: column;
}

.message_body {
  padding: 1em;
  background-color: var(--theme-message-bg);
  color: var(--theme-message-fg);
  border-radius: 20px;
  display: inline-block;
  align-self: flex-start;
}

.from_me > .message_body {
  background-color: var(--theme-message-from_me-bg);
  color: var(--theme-message-from_me-fg);
  align-self: flex-end;
}

.metadata {
  align-self: flex-start;
}

.from_me > .metadata {
  align-self: flex-end;
}

.metadata > .sender {
  font-size: 0.8em;
  color: #666;
}

.metadata > .timestamp {
  font-size: 12px;
  color: #888;
}

.message_media img {
  max-width: 100%;
}
</style>
