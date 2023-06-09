<!-- 
This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
See LICENSE.txt for full details.
Copyright 2023 Telemarq Ltd
-->

<script setup>
import { ref, watch, computed } from 'vue'
import { useQuery } from '@vue/apollo-composable'
import gql from 'graphql-tag'

import ContactCardSmall from './ContactCardSmall.vue'
import { activeDevices, contactsFilter, setFilter } from '../store.js'

const searchTypeRestrict = ref(false);
const searchTimeRestrict = ref(false);
const searchTimeStart = ref(null);
const searchTimeEnd = ref(null);
const searchParticipantsRestrict = ref(false);
const selectedMergedContacts = ref({});


const eventTypes = ref([
	{'type': 'MessageEvent', 'name': 'Messages', 'selected': false}
]);

const { result: contactsResult } = useQuery( gql`
	query getContacts($deviceIds: [String]!, $filter: ContactsFilter) {
		contacts(deviceIds: $deviceIds, filter: $filter) {
            contacts {
				id
				deviceId
				providerName
				providerFriendlyName
				name{first last display}
				email
				phone
			}
			mergedContacts {
				id
				name{first last display}
				phone
				mergedIds
			}
		}
	}
`, {
	deviceIds: activeDevices,
	filter: contactsFilter
});

const contacts = computed(() => {
	/* Return a hash mapping merged contact ID to list of contacts */
	if (contactsResult.value && contactsResult.value.contacts) {
		let contactsMap = {};
		for (let contact of contactsResult.value.contacts.contacts) {
			contactsMap[contact.id] = contact;
		}
		let mergedContactsMap = {};
		for (let mergedContact of contactsResult.value.contacts.mergedContacts) {
			mergedContactsMap[mergedContact.id] = mergedContact.mergedIds.map((id) => contactsMap[id]);
		}
		return mergedContactsMap;
	} else {
		return {};
	}
});

const mergedContacts = computed(() => {
	if (contactsResult.value && contactsResult.value.contacts) {
		return contactsResult.value.contacts.mergedContacts;
	} else {
		return [];
	}
});

function selectMergedContact(mergedContact) {
	selectedMergedContacts.value[mergedContact.id] = !(!!selectedMergedContacts.value[mergedContact.id]);
	updateGql();  // changing dict entries doesn't trigger watch
}

function parseGql() {
	/* Parse the graphql filter into individual parameters for the UI */
}

function updateGql() {
	/* Update the graphql filter from the UI parameters */
	let filter = {};

	if (searchTypeRestrict.value) {
		filter.typeNames = eventTypes.value.filter((type) => type.selected).map((type) => type.type);
	}

	if (searchParticipantsRestrict.value) {
		filter.participantIds = [];
		// Push actual contact ID lists from merged contacts
		for (let mergedContactId of Object.keys(selectedMergedContacts.value)) {
			if (selectedMergedContacts.value[mergedContactId]) {
				filter.participantIds.push(...contacts.value[mergedContactId].map((contact) => contact.id));
			}
		}
	}

	if (searchTimeRestrict.value) {
		filter.timestampStart = searchTimeStart.value;
		filter.timestampEnd = searchTimeEnd.value;
	}

	setFilter(filter);
}

watch([searchTypeRestrict, searchTimeRestrict, searchTimeStart, searchTimeEnd, searchParticipantsRestrict, selectedMergedContacts], () => {
	updateGql();
});

</script>

<template>
	<div id="view">
		<h1>Filter</h1>

		<form>
			<!-- Restrict based on message type -->
			<div class="searchStanza">
				<input type="checkbox" v-model="searchTypeRestrict" id="searchTypeRestrictCheckbox">
				<label for="searchTypeRestrictCheckbox"> Limit the type of result</label>

				<div v-if="searchTypeRestrict" class="searchOption">
					<div v-for="eventType of eventTypes" :key="eventType.type">
						<input type="checkbox" v-model="eventType.selected" :value="eventType.type" :id="'searchTypeRestrict' + eventType.type" @change="updateGql()">
						<label :for="'searchTypeRestrict' + eventType.type"> {{ eventType.name }}</label>
					</div>
				</div>
			</div>

			<!-- Restrict based on time -->
			<div class="searchStanza">
				<input type="checkbox" v-model="searchTimeRestrict" id="searchTimeRestrictCheckbox">
				<label for="searchTimeRestrictCheckbox"> Between a time range </label>
				<div v-if="searchTimeRestrict" class="searchOption">
					<div>
						<label for="searchTimeRestrictStart">S:</label>
						<input type="datetime-local" v-model="searchTimeStart" id="searchTimeRestrictStart">
					</div>
					<div>
						<label for="searchTimeRestrictEnd">E:</label>
						<input type="datetime-local" v-model="searchTimeEnd" id="searchTimeRestrictEnd">
					</div>
				</div>
			</div>

			<!-- Restrict based on participants -->
			<div class="searchStanza">
				<input type="checkbox" v-model="searchParticipantsRestrict" id="searchParticipantsRestrictCheckbox">
				<label for="searchParticipantsRestrictCheckbox"> Limit to contacts </label>
				<div v-if="searchParticipantsRestrict" class="searchOption">
					<ContactCardSmall
						v-for="mergedContact of mergedContacts"
						:key="mergedContact.id"
						:mergedContact="mergedContact"
						:rawContacts="contacts[mergedContact.id]"
						:selected="selectedMergedContacts[mergedContact.id] || false"
						@click="selectMergedContact(mergedContact)"
					/>
				</div>
			</div>
		</form>
	</div>
</template>

<style scoped>

.searchOption {
	margin-left: 1em;
}


</style>
