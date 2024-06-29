<!--
This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
See LICENSE.txt for full details.
Copyright 2023 Telemarq Ltd
-->

<!--
Component responsible for displaying an input field and making a mutation
request to the GraphQL API.
-->

<script setup>
import { ref } from 'vue';

import { useMutation } from '@vue/apollo-composable';
import gql from 'graphql-tag';

const { mutate: decryptDevice, onDone } = useMutation(gql`
  mutation decryptDevice($deviceId: String!, $passphrase: String!) {
    decryptDevice(deviceId: $deviceId, passphrase: $passphrase)
  }
`);

const props = defineProps({
  deviceId: String,
});

const showPassphraseInput = ref(false);
const showWrongPassphraseMessage = ref(false);
const passphrase = ref('');

onDone((result) => {
  if (result.data && !result.data.decryptDevice) {
    showWrongPassphraseMessage.value = true;
    passphrase.value = '';
  } else if (result.data && result.data.decryptDevice) {
    showWrongPassphraseMessage.value = false;
    passphrase.value = '';
  }
});
</script>

<template>
  <div class="encrypted">
    <span class="decrypt" @click="showPassphraseInput = !showPassphraseInput"
      >&#128273;</span
    >
    <span
      class="wrong-passphrase"
      v-show="showWrongPassphraseMessage"
      title="Wrong passphrase: could not decrypt files."
      >&#9888;</span
    >
  </div>

  <div class="container" v-if="showPassphraseInput">
    <input
      type="password"
      v-model="passphrase"
      placeholder="Type passphrase..."
    />
    <button
      @click="
        decryptDevice({
          deviceId: props.deviceId,
          passphrase: passphrase,
        })
      "
    >
      Decrypt
    </button>
  </div>
</template>

<style scoped>
.decrypt {
  font-size: 14px;
  text-align: center;
  cursor: pointer;
}

.encrypted {
  display: inline-block;
}

.wrong-passphrase {
  color: red;
}

.container {
  display: grid;
  grid-template-columns: 70% 30%;
}

span {
  margin-left: 10px;
}
</style>
