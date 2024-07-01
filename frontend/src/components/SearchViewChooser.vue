<!-- 
This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
See LICENSE.txt for full details.
Copyright 2023 Telemarq Ltd
-->
<script setup>
import { searchView, setSearchView } from '../store.js';

const props = defineProps({});
</script>

<template>
  <ul>
    <li
      :class="{ active: searchView == 'messages' }"
      @click="setSearchView('messages')"
    >
      Messages
    </li>
    <li
      :class="{ active: searchView == 'media' }"
      @click="setSearchView('media')"
    >
      Media
    </li>
  </ul>
</template>

<style scoped>
/* Tab bar */
ul {
  list-style-type: none;
  margin: 0;
  padding: 0;
  overflow: hidden;
  background-color: #333;
}
li {
  display: inline-block;
  padding: 0.5em 1em;
  background-color: #aaa;
  border-right: 1px solid black;
  cursor: pointer;
}
li.active {
  background-color: white;
}
</style>
