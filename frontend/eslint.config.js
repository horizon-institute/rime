import pluginJs from '@eslint/js';
import pluginVue from 'eslint-plugin-vue';
import eslintConfigPrettier from 'eslint-config-prettier';

export default [
  pluginJs.configs.recommended,

  ...pluginVue.configs['flat/essential'],

  eslintConfigPrettier,

  {
    files: ['**/*.{js,mjs,cjs,vue}'],

    rules: {
      'no-unused-vars': 'warn',
      'no-extra-boolean-cast': 'warn',
    },
  },

  {
    files: ['**/*.vue'],
    rules: {
      'vue/require-v-for-key': 'warn',
      'vue/multi-word-component-names': 'warn',
      'vue/no-side-effects-in-computed-properties': 'warn',
    },
  },
];
