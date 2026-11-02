<script setup lang="ts">
import DefaultTheme from 'vitepress/theme'
import { useData, withBase } from 'vitepress'
import CourseHome from './components/CourseHome.vue'
import SourceViewer from './components/SourceViewer.vue'
const { frontmatter } = useData()
const names: Record<string, string> = { easyspider: 'EasySpider', openclaw: 'OpenClaw', llamafactory: 'LLaMAFactory', langchain: 'LangChain', minimind: 'MiniMind' }
</script>

<template>
  <DefaultTheme.Layout>
    <template #page-top>
      <CourseHome v-if="frontmatter.courseLayout === 'home'" />
      <SourceViewer v-if="frontmatter.courseLayout === 'source'" />
    </template>
    <template #doc-before>
      <div v-if="frontmatter.project" class="lecture-eyebrow">
        <a :href="withBase('/' + frontmatter.project + '/')">{{ names[frontmatter.project] }}</a>
        <span>/</span><span>{{ frontmatter.projectOverview ? '项目导读' : '课程讲义' }}</span>
      </div>
    </template>
    <template #doc-after>
      <aside v-if="frontmatter.sourcePath" class="original-note">
        <div><span class="meta-label">讲义来源</span><p>{{ frontmatter.sourcePath }}</p></div>
        <a :href="withBase(frontmatter.originalUrl)" download>{{ frontmatter.downloadLabel || '下载原始 Markdown' }} <span aria-hidden="true">↗</span></a>
      </aside>
    </template>
  </DefaultTheme.Layout>
</template>
