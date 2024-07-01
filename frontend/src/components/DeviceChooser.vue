<!--
This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
See LICENSE.txt for full details.
Copyright 2023 Telemarq Ltd
-->

<script setup>
import { watch, nextTick } from 'vue';
import {
  devices,
  activeDevices,
  deleteDevice,
  setDeviceSelected,
} from '../store.js';

import DeviceDecryptWidget from './DeviceDecryptWidget.vue';

/* When activeDevices changes, update the check boxes. */
watch(activeDevices, (newVal, oldVal) => {
  nextTick(() => {
    devices.value.forEach((device) => {
      const cb = document.getElementById('device-' + device.id);
      if (!cb) return;

      cb.checked = newVal.includes(device.id);
    });
  });
});

async function toggleDeviceActive(id) {
  const cb = document.getElementById('device-' + id);
  if (!cb) return;

  await setDeviceSelected(id, cb.checked);
}
</script>

<template>
  <div id="view">
    <h1>Devices</h1>
    <div v-for="device in devices">
      <input
        type="checkbox"
        :id="'device-' + device.id"
        :key="device.id"
        :value="device.id"
        :label="device.id"
        @click="toggleDeviceActive(device.id)"
        :disabled="device.is_locked"
      />
      <label
        :class="{ locked: device.is_locked }"
        :for="'device-' + device.id"
        >{{ device.id }}</label
      >
      <span class="country_code">{{ device.country_code }}</span>
      <span v-if="device.is_encrypted">
        <DeviceDecryptWidget :deviceId="device.id" />
      </span>
      <div
        class="delete"
        v-if="device.is_subset && !device.is_locked"
        @click="deleteDevice(device.id)"
      >
        &#10060;
      </div>
    </div>
    <div v-if="devices.length === 0">
      <p>No data detected.</p>
      <p class="text-box">
        You can configure the location of the device data in the
        <code>rime_settings.yaml</code> or
        <code>rime_settings.local.yaml</code>
        file and restart the server. Each device in the directory will appear in
        a list here.
      </p>
    </div>
  </div>
</template>

<style scoped>
.delete {
  display: inline-block;
  color: red;
  font-size: 8px;
  text-align: center;
  float: right;
  cursor: pointer;
}

.country_code {
  padding-left: 0.5em;
  font-size: 0.7em;
  color: #888;
  cursor: default;
}

label.locked {
  color: #888;
  cursor: default;
}

/* Github-style inline code formatting: https://stackoverflow.com/a/22997770 */
pre {
  border-radius: 5px;
  -moz-border-radius: 5px;
  -webkit-border-radius: 5px;
  border: 1px solid #bcbec0;
  background: #f1f3f5;
  font:
    12px Monaco,
    Consolas,
    'Andale  Mono',
    'DejaVu Sans Mono',
    monospace;
}

code {
  border-radius: 5px;
  -moz-border-radius: 5px;
  -webkit-border-radius: 5px;
  border: 1px solid #bcbec0;
  padding: 2px;
  font:
    12px Monaco,
    Consolas,
    'Andale  Mono',
    'DejaVu Sans Mono',
    monospace;
}

pre code {
  border-radius: 0px;
  -moz-border-radius: 0px;
  -webkit-border-radius: 0px;
  border: 0px;
  padding: 2px;
  font:
    12px Monaco,
    Consolas,
    'Andale  Mono',
    'DejaVu Sans Mono',
    monospace;
}
</style>
