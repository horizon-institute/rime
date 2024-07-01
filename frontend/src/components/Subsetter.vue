<!-- 
This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
See LICENSE.txt for full details.
Copyright 2023 Telemarq Ltd
-->
<script setup>
import { useMutation } from '@vue/apollo-composable';
import { ref } from 'vue';
import gql from 'graphql-tag';

import {
  eventsFilter,
  hasEventsFilter,
  contactsFilter,
  activeDevices,
  setDeviceSelected,
} from '../store.js';

const newDeviceId = ref('');
const anonymise = ref(false);

const emit = defineEmits(['createdNewSubset', 'showPopover']);

const { mutate: createSubset } = useMutation(gql`
  mutation createSubset(
    $targets: [DeviceIdPair]!
    $eventsFilter: EventsFilter
    $contactsFilter: ContactsFilter
    $anonymise: Boolean
  ) {
    createSubset(
      targets: $targets
      eventsFilter: $eventsFilter
      contactsFilter: $contactsFilter
      anonymise: $anonymise
    )
  }
`);

function canCreateFilter() {
  return hasEventsFilter() && activeDevices.value.length >= 1;
}

async function createFilter() {
  if (!canCreateFilter()) {
    return;
  }

  const device = activeDevices.value[0];
  const targets = [];

  if (activeDevices.value.length == 1) {
    /* newDeviceId is a name */
    targets.push({ oldDeviceId: device, newDeviceId: newDeviceId.value });

    /* Ensure we don't start selected if the name was used previously */
    setDeviceSelected(newDeviceId.value, false);
  } else {
    /* newDeviceId is a prefix */
    for (const device of activeDevices.value) {
      targets.push({
        oldDeviceId: device,
        newDeviceId: newDeviceId.value + device,
      });
      setDeviceSelected(newDeviceId.value + device, false);
    }
  }

  try {
    const result = await createSubset({
      targets: targets,
      eventsFilter: eventsFilter.value,
      contactsFilter: contactsFilter.value,
      anonymise: anonymise.value,
    });

    if (result.data.createSubset) {
      emit('createdNewSubset', targets);
    }
  } catch (e) {
    if (e.graphQLErrors) {
      const errors = [];
      for (const error of e.graphQLErrors) {
        errors.push(error.message);
      }

      const message = errors.join('\n');
      emit('showPopover', message);
    }
    return;
  }
}
</script>

<template>
  <div id="view">
    <h1>Subset</h1>
    <div v-if="canCreateFilter()">
      <p v-if="activeDevices.length == 1">Subset to a new device.</p>
      <p v-else>Subset to new devices.</p>
      <div v-if="activeDevices.length == 1">
        Name: <input type="text" v-model="newDeviceId" />
      </div>
      <div v-else>Prefix: <input type="text" v-model="newDeviceId" /></div>
      <div>
        <input type="checkbox" v-model="anonymise" id="cb_anonymise" />
        <label for="cb_anonymise">Anonymise</label>
      </div>
      <div>
        <button
          :class="{ disabled: !canCreateFilter() }"
          @click="createFilter()"
        >
          Create device
        </button>
      </div>
    </div>
    <div v-else>
      <p>Select a device and a filter.</p>
    </div>
  </div>
</template>

<style scoped>
#subsetter button {
  margin: 12px 0;
}
</style>
