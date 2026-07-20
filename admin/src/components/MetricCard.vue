<script setup lang="ts">defineProps<{label:string,value:string|number,tone?:string,note?:string}>();</script>
<template><article class="metric-card" :class="tone"><span>{{label}}</span><strong>{{value}}</strong><small>{{note||'实时数据'}}</small></article></template>
