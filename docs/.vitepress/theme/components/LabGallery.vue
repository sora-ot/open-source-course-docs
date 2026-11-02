<script setup lang="ts">
import { ref } from 'vue'
import { withBase } from 'vitepress'
const selected = ref(-1)
const demos = [
  { name: 'XPath、匹配与 DFS', desc: '把页面元素定位与树遍历的过程放在一起观察。', path: '附录A.交互式图解-XPath匹配与DFS.html', tag: '算法图解' },
  { name: '流程图的三个数组', desc: '观察流程图数据结构、节点顺序与 refresh 的关系。', path: '附录B.交互式图解-流程图三数组与refresh.html', tag: '数据结构' },
  { name: '同类元素匹配', desc: '在一个小页面上理解同类元素怎样被定位和选择。', path: '示例-同类元素匹配/index.html', tag: '网页示例' },
]
const videos = [
  { name: 'EasySpider', file: 'easyspider.mp4', desc: '观察可视化采集的操作过程。' },
  { name: 'OpenClaw', file: '一个视频搞懂OpenClaw.mp4', desc: '从演示建立智能体系统的整体印象。' },
  { name: 'LLaMAFactory', file: 'llamafactory演示.mp4', desc: '认识训练框架的操作与使用场景。' },
  { name: 'LangChain', file: 'langchain.mp4', desc: '配合十分钟讲义理解组件调用。' },
]
function demoUrl(path: string) { return withBase('/resources/easyspider/' + path) }
</script>

<template>
  <main class="labs-page">
    <div class="eyebrow">LEARNING BY DOING</div><h1>让过程，看得见。</h1><p class="labs-intro">用图解追踪结构，用演示连接原理与真实运行。</p>
    <div class="section-heading"><h2>交互图解</h2><span>EasySpider / 配套材料</span></div>
    <div class="demo-grid"><article v-for="(demo, i) in demos" :key="demo.name" class="demo-card"><span class="demo-tag">{{ demo.tag }}</span><h3>{{ demo.name }}</h3><p>{{ demo.desc }}</p><div><button @click="selected = i">在此打开 →</button><a :href="demoUrl(demo.path)" target="_blank" rel="noopener">独立窗口 ↗</a></div></article></div>
    <section v-if="selected >= 0" class="demo-frame"><div class="demo-frame-title"><strong>{{ demos[selected].name }}</strong><button @click="selected = -1">关闭预览 ×</button></div><iframe :key="selected" :src="demoUrl(demos[selected].path)" :title="demos[selected].name" sandbox="allow-scripts allow-same-origin" loading="lazy"></iframe></section>
    <div class="section-heading videos-heading"><h2>项目演示</h2><span>课堂配套视频</span></div>
    <div class="video-grid"><article v-for="video in videos" :key="video.file" class="video-card"><video :aria-label="video.name + ' 演示视频'" controls preload="none" playsinline><source :src="withBase('/resources/videos/' + video.file)" type="video/mp4">你的浏览器不支持视频播放，可以下载后观看。</video><div><h3>{{ video.name }}</h3><p>{{ video.desc }}</p><a :href="withBase('/resources/videos/' + video.file)" download>下载视频 ↗</a></div></article></div>
    <div class="lab-bottom"><p>Selenium、浏览器扩展和训练代码需要按讲义在本机环境运行。</p><a :href="withBase('/guide/')">回到学习路线 →</a></div>
  </main>
</template>
