// This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
// See LICENSE.txt for full details.
// Copyright 2023 Telemarq Ltd

import { ref, computed, watch } from 'vue';
import { ApolloClient, InMemoryCache } from '@apollo/client/core'
import { useQuery, useMutation, useSubscription, provideApolloClient } from '@vue/apollo-composable'
import { useLocalStorage } from '@vueuse/core'
import gql from 'graphql-tag'


import { GraphQLWsLink } from '@apollo/client/link/subscriptions';
import { createClient } from 'graphql-ws';

/* GraphQL integration */
const backendUrl = import.meta.env.RIME_BACKEND || '';
const wsLink = new GraphQLWsLink(createClient({
    url: backendUrl + '/graphql-ws',
}));

export const apolloClient = new ApolloClient({
    link: wsLink,
    cache: new InMemoryCache(),
});

provideApolloClient(apolloClient);

const { mutate: setDevicePropertiesMutation } = useMutation( gql`
	mutation setDeviceProperties($id: String!, $properties: SetDeviceProperties!) {
		setDeviceProperties(deviceId: $id, deviceProperties: $properties)
	}
`);

const { mutate: deleteDeviceMutation } = useMutation( gql`
	mutation deleteDevice($id: String!) {
		deleteDevice(deviceId: $id)
	}
`);

export const devices = ref([]);

const devicesSubscription = gql`
    subscription OnDevicesChanged {
        devicesChanged {
            id
            is_subset
            is_locked
            country_code
        }
    }
`;

const { result: devicesGqlResult } = useSubscription(devicesSubscription);

watch(devicesGqlResult, (data) => {
    devices.value = data.devicesChanged;
});

const selectedDevices = useLocalStorage('selectedDevices', []);

export const activeDevices = computed(() => {
    return devices.value.filter(d => selectedDevices.value.includes(d.id)).map(d => d.id);
});

export async function setDeviceSelected(id, isSelected) {
    if(isSelected) {
        selectedDevices.value.push(id);
    } else {
        selectedDevices.value = selectedDevices.value.filter(d => d !== id);
    }
}

export async function deleteDevice(id) {
    await deleteDeviceMutation({ "id": id });
}

export const contactsFilter = ref({ });
export const eventsFilter = ref({ });

export function hasEventsFilter() {
    return Object.keys(eventsFilter.value).length > 0;
}

export function setFilter(filter) {
    eventsFilter.value = filter;
}
