<!-- 
This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
See LICENSE.txt for full details.
Copyright 2023 Telemarq Ltd
-->
<script setup>
import { ref } from 'vue'

import DeviceChooser from './DeviceChooser.vue'
import Search from './Search.vue'
import Subsetter from './Subsetter.vue'
import ProviderChooser from './ProviderChooser.vue'
import SearchViewChooser from './SearchViewChooser.vue'
import SearchResults from './SearchResults.vue'
import SearchResultsMedia from './SearchResultsMedia.vue'

import { searchView } from '../store.js'

const showRefinements = ref(false);

const popoverMessage = ref('This is the popover message');

function showPopover(message) {
	const popover = document.getElementById('popover');
	popover.innerHTML = message;
	popover.style.animation = 'fadein 1s linear';
	popover.style.display = 'block';
	setTimeout(() => {
		popover.style.animation = 'fadeout 1s linear';
		setTimeout(() => {
			popover.style.display = 'none';
		}, 1000);
	}, 5000);
}

</script>

<template>
	<div id="view">
		<div id="left" class="search">
			<img id="logo" src="/logo.png" />
			<DeviceChooser id="deviceChooser"/>
			<Search id="search"/>
			<Subsetter id="subsetter" @showPopover="showPopover" />
		</div>

		<div id="right">
			<SearchViewChooser id="searchViewChooser"/>
			<SearchResults v-show="searchView == 'messages'" id="searchResults"/>
			<SearchResultsMedia v-show="searchView == 'media'" id="searchResults"/>
		</div>

		<div id="popover">
			<p>{{ popoverMessage }}</p>
		</div>
	</div>
</template>

<style scoped>

#view {
	display: flex;
	width: 100%;
	height: 100vh;
}

#left {
	width: 18em;
	border-right: 1px solid #ccc;
	overflow-y: auto;
	height: 100vh;
	flex-shrink: 0;
}

#right {
	flex-grow: 1;
	height: 100vh;
	display: flex;
	flex-direction: column;
}

#searchViewChooser {
	border-bottom: 1px solid #ccc;
	flex-grow: 0;
	flex-shrink: 0;
}

#searchResults {
	flex-grow: 1;
	overflow-y: auto;
}

#deviceChooser {
	margin: 1em;
}

#search {
	margin: 1em;
}

#subsetter {
	margin: 1em;
}

#popover {
	position: absolute;
	width: 40em;
	height: 6em;
	top: 0;
	left: calc(50% - 20em);
	background-color: #E30B5Cee;
	border-radius: 0 0 1em 1em;
	padding-left: 1em;
	padding-right: 1em;
	color: white;
	font-weight: 700;
	z-index: 100;
	text-align: center;
	display: none;
}

</style>
