<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useData, withBase } from 'vitepress'
const props = defineProps<{ encoded: string }>()
const { isDark } = useData()
const svg = ref('')
const error = ref(false)
const source = ref('')
async function render() {
  try {
    const text = new TextDecoder().decode(Uint8Array.from(atob(props.encoded), c => c.charCodeAt(0)))
    source.value = text
    const moduleUrl = withBase('/assets/vendor/mermaid/mermaid.esm.min.mjs')
    const { default: mermaid } = await import(/* @vite-ignore */ moduleUrl)
    mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: isDark.value ? 'dark' : 'neutral', fontFamily: 'system-ui, sans-serif' })
    const result = await mermaid.render('diagram-' + Math.random().toString(36).slice(2), text)
    svg.value = result.svg
    error.value = false
  } catch { error.value = true }
}
onMounted(render)
watch(isDark, render)
</script>

<template><div class="mermaid-diagram"><div v-if="svg && !error" v-html="svg"></div><details :open="error"><summary>{{ error ? '图表暂无法渲染，查看流程描述' : '查看图表源码' }}</summary><pre>{{ source }}</pre></details></div></template>
