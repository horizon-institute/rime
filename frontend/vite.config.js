// This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
// See LICENSE.txt for full details.
// Copyright 2023 Telemarq Ltd

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [vue()],
    server : {
        host: 'localhost',
        port: 3000,
        strictPort: true,
    },
    base: '/rime/',
    envDir: './',
    envPrefix: 'RIME',
    clearScreen: false,
})
