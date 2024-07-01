<!-- Displays a selectable contact with hoverable information -->
<script setup>
import { ref } from 'vue';

const props = defineProps({
  mergedContact: {
    type: Object,
    required: true,
  },
  rawContacts: {
    type: Array,
    required: true,
  },
  selected: {
    type: Boolean,
    required: true,
  },
});

function contactName(contact) {
  if (contact.name.display) {
    return contact.name.display;
  } else if (contact.name.first && contact.name.last) {
    return contact.name.first + ' ' + contact.name.last;
  } else {
    return contact.email;
  }
}

const showMerged = ref(false);
</script>

<template>
  <div id="view" :class="{ selected: selected }">
    <div id="name" :class="{ selected: selected }">
      {{ contactName(mergedContact) }}
    </div>
    <div id="details">
      <span id="phone">{{ mergedContact.phone }}</span>
      <div
        id="toggleMerged"
        v-if="rawContacts.length > 1"
        @click.stop="showMerged = !showMerged"
      >
        {{ showMerged ? 'Hide' : 'Show' }} merged contacts
      </div>
      <div
        id="merged"
        v-if="rawContacts.length > 1"
        :class="{ showMerged: showMerged }"
      >
        <div v-for="contact in rawContacts" :key="contact.id">
          {{ contactName(contact) }} ({{ contact.providerFriendlyName }})
        </div>
      </div>
      <!-- span id="provider" :title="'Provider: ' + contact.providerFriendlyName"><div id="infobox">i</div></span-->
    </div>
  </div>
</template>

<style scoped>
#view {
  background: #ddd;
  border-radius: 0.5em;
  padding: 0.5em;
  margin-top: 0.5em;
  margin-bottom: 0.5em;
  color: #444;
}

#view.selected {
  background: #44c;
  color: white;
}

#name {
}

#name.selected {
  font-weight: bold;
}

#details {
  font-size: 10px;
}

#toggleMerged {
  font-size: 9px;
  cursor: pointer;
}

#merged {
  font-size: 9px;
  padding: 0.5em;
  margin: 0.5em;
  border-radius: 0.5em;
  background: #eee;
  display: none;
}

#merged.showMerged {
  display: block;
}

.selected #merged {
  background: #88f;
}

#infobox {
  width: 2em;
  text-align: center;
  border: 1px solid #ccc;
  display: inline-block;
  cursor: help;
  border-radius: 3px;
  margin-left: 0.5em;
}
</style>
