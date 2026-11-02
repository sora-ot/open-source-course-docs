<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { withBase } from 'vitepress'
const path = ref('')
const text = ref('')
const error = ref('')
const loading = ref(true)
const key = ref('')
const targetLine = ref(0)
const keyword = ref('')
const copied = ref(false)
const lines = computed(() => text.value.split('\n'))
const matches = computed(() => keyword.value ? lines.value.reduce<number[]>((a, l, i) => l.toLowerCase().includes(keyword.value.toLowerCase()) ? [...a, i + 1] : a, []) : [])
const index = ref(0)

async function jump(line: number) {
  targetLine.value = line
  await nextTick()
  document.getElementById('L' + line)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}
function find() {
  if (!matches.value.length) return
  index.value = (index.value + 1) % matches.value.length
  jump(matches.value[index.value])
}
async function copy() {
  try { await navigator.clipboard.writeText(text.value); copied.value = true; setTimeout(() => copied.value = false, 1800) } catch { copied.value = false }
}
onMounted(async () => {
  try {
    key.value = new URLSearchParams(location.search).get('file') || ''
    const response = await fetch(withBase('/source-files.json'))
    if (!response.ok) throw new Error('无法读取源码索引')
    const files = await response.json()
    if (!Object.hasOwn(files, key.value)) throw new Error('请选择讲义正文中的源码链接，当前文件不在引用索引中。')
    path.value = files[key.value].path
    const codeResponse = await fetch(withBase('/resources/sources/' + key.value))
    if (!codeResponse.ok) throw new Error('无法读取源码快照')
    text.value = (await codeResponse.text()).replace(/\r\n/g, '\n')
    loading.value = false
    const line = Number(location.hash.match(/^#L(\d+)/)?.[1])
    if (line) setTimeout(() => jump(line), 80)
  } catch (e) { error.value = e instanceof Error ? e.message : '加载失败'; loading.value = false }
})
</script>

<template>
  <main class="source-page">
    <div class="eyebrow">FOLLOW THE SOURCE</div><h1>对照源码，继续追踪。</h1>
    <p class="source-subtitle">讲义所引用的本地源码快照。行号用于对照课堂内容。</p>
    <p v-if="loading" role="status">正在加载源码…</p>
    <div v-else-if="error" role="alert" class="source-error">{{ error }} <a :href="withBase('/guide/')">返回学习路线 →</a></div>
    <template v-else>
      <div class="source-toolbar"><div class="source-filepath">{{ path }}<small>{{ lines.length }} 行</small></div><div class="source-actions"><input v-model="keyword" type="search" aria-label="在源码中查找" placeholder="查找代码…" @input="index = -1" @keydown.enter="find"><button @click="find">查找{{ keyword ? ' · ' + matches.length : '' }}</button><button @click="copy">{{ copied ? '已复制' : '复制' }}</button><a :href="withBase('/resources/sources/' + key)" :download="path.split('/').pop()">下载</a></div></div>
      <div class="source-code" tabindex="0" aria-label="带行号的源码">
        <div v-for="(line, i) in lines" :id="'L' + (i + 1)" :key="i" :class="['source-line', { selected: i + 1 === targetLine, matched: keyword && line.toLowerCase().includes(keyword.toLowerCase()) }]"><a :href="'#L' + (i + 1)" :aria-label="'第 ' + (i + 1) + ' 行'" @click="targetLine = i + 1">{{ i + 1 }}</a><code>{{ line || ' ' }}</code></div>
      </div>
    </template>
  </main>
</template>
