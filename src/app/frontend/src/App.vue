<template>
  <router-view />
  <transition name="toast">
    <div v-if="message" class="toast">{{ message }}</div>
  </transition>
</template>

<script setup lang="ts">
import { useToast } from '@/composables/toast'
const { message } = useToast()
</script>
