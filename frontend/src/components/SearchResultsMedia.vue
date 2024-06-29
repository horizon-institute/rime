<!--
This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
See LICENSE.txt for full details.
Copyright 2023 Telemarq Ltd
-->
<script setup>
import {
  activeDevices,
  rawEventsSearchResult,
  eventsSearchResultById,
} from '../store.js';
import SearchResultMediaEvent from './SearchResultMediaEvent.vue';

import { watch, ref, computed } from 'vue';

const menuitems = ref(null);
const menuDownloadUrl = ref(null);
const showNonUserGeneratedEvents = ref(false);

const toggleMenu = function (event) {
  const menu = event.target.closest('.menu');

  if (menuitems.value.parentNode) {
    menuitems.value.parentNode.removeChild(menuitems.value);
    menuitems.value.style.display = 'none';
  }

  if (menu) {
    if (menu.classList.contains('open')) {
      menu.classList.remove('open');
    } else {
      menu.classList.add('open');
      menu.appendChild(menuitems.value);
      menuitems.value.style.display = 'block';

      menuDownloadUrl.value =
        eventsSearchResultById.value[menu.dataset.eventid].url;
    }
  }
  /* Close all other menus */
  const menus = document.querySelectorAll('.menu.open');
  for (const otherMenu of menus) {
    if (otherMenu == menu) {
      continue;
    }
    otherMenu.classList.remove('open');
  }
};

const eventsByCategory = computed(() => {
  /*
	   Sort media events into generic event categories.

	   We get categories from generic providers, which are those which span multiple apps.
	 */
  const events = rawEventsSearchResult.value.events.events;
  const eventsByCategory = {
    'no category': [],
  };
  for (const event of events) {
    if (!event || event.__typename != 'MediaEvent') {
      continue;
    }

    if (event.genericEventInfo) {
      if (!eventsByCategory[event.genericEventInfo.category]) {
        eventsByCategory[event.genericEventInfo.category] = [];
      }
      eventsByCategory[event.genericEventInfo.category].push(event);
    } else {
      eventsByCategory['no category'].push(event);
    }
  }

  if (eventsByCategory['no category'].length == 0) {
    delete eventsByCategory['no category'];
  }
  return eventsByCategory;
});

const shouldShowEvent = function (event) {
  return (
    event &&
    event.__typename == 'MediaEvent' &&
    (showNonUserGeneratedEvents.value || event.genericEventInfo.isUserGenerated)
  );
};
</script>

<template>
  <div v-if="rawEventsSearchResult">
    <div id="menuitems" ref="menuitems">
      <ul>
        <li><a :href="menuDownloadUrl" target="_blank">Download</a></li>
      </ul>
    </div>
    <div>
      <input
        type="checkbox"
        v-model="showNonUserGeneratedEvents"
        id="showNonUserGeneratedEvents"
      />
      <label for="showNonUserGeneratedEvents"
        >Show non-user-generated events</label
      >
    </div>
    <div
      class="category"
      v-for="[category, events] of Object.entries(eventsByCategory)"
    >
      <div class="categoryName">
        {{ category }}
      </div>
      <div class="grid">
        <template v-for="event in events">
          <div v-if="shouldShowEvent(event)" class="gridElement">
            <div class="menu" :data-eventid="event.id">
              <div class="burger" @click="toggleMenu">&vellip;</div>
            </div>
            <video v-if="event.mime_type.startsWith('video')" controls>
              <source :src="event.url" :type="event.mime_type" />
            </video>
            <img v-else :src="event.url" />
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.category {
  width: 100%;
}

.categoryName {
  font-weight: bold;
  padding: 0.5em;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  grid-gap: 1px;
}

.gridElement {
  position: relative; /* for the menu */
}

.menu {
  position: absolute;
  top: 0;
  right: 0;
  text-align: right;
  cursor: pointer;
  z-index: 1;
}

.menu.open {
  background-color: #eeea;
}

#menuitems {
  display: none;
  position: relative;
  top: 0;
  right: 0;
  padding: 0.5em;
  z-index: 1;
}

#menuitems ul {
  list-style-type: none;
  margin: 0;
  padding: 0;
}

img {
  max-width: 100%;
}

video {
  max-width: 100%;
}
</style>
