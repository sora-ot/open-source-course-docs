<script setup lang="ts">
import { computed, ref } from 'vue'
import { withBase } from 'vitepress'
import projects from '../../projects.json'
import stats from '../../stats.json'
const current = ref(0)
const active = computed(() => projects[current.value])
const stages = [
  ['选择网页元素', '生成任务 JSON', '自动采集数据'],
  ['接收用户消息', '模型调用工具', '汇总任务结果'],
  ['适配数据与模型', '构造训练样本', 'Trainer 更新参数'],
  ['Prompt 格式化', 'Model 生成回复', 'Parser 解析输出'],
  ['文本变成 Token', '预训练与 SFT', 'Rollout 与 PPO 更新'],
]
const code = [
  ['task = record(page.selection)', 'graph = build_flowchart(task)', 'execute(graph, browser)'],
  ['session.prompt("帮我完成任务")', 'await agent.call(tool, params)', 'return summarize(results)'],
  ['dataset = align_dataset(data)', 'model = init_adapter(model)', 'trainer.train()'],
  ['chain = prompt | model | parser', 'result = chain.invoke(question)', 'print(result)'],
  ['logits = model(input_ids)', 'loss = next_token_loss(logits, labels)', 'loss.backward(); optimizer.step()'],
]
</script>

<template>
  <main class="course-home">
    <section class="course-hero">
      <div class="hero-copy">
        <div class="eyebrow"><span class="status-dot"></span> OPEN SOURCE · COURSE NOTES</div>
        <h1>从源码出发，<br>理解软件<span class="accent-text">如何运转。</span></h1>
        <p class="hero-description">沿着真实项目的数据流与调用链，<br class="desktop-break">把抽象原理、代码实现和动手实践连起来。</p>
        <div class="hero-actions">
          <a class="button-primary" href="#projects">浏览项目讲义 <span aria-hidden="true">↘</span></a>
        </div>
        <div class="hero-footnote"><span class="mini-rule"></span> 以问题为起点 · 以完整流程为主线</div>
      </div>
      <div class="flow-workbench" aria-label="项目调用流程预览">
        <div class="workbench-top"><div class="window-dots"><i></i><i></i><i></i></div><span>从一个输入，到一次完整执行</span><span class="live-dot"></span></div>
        <div class="workbench-tabs" role="tablist" aria-label="选择项目流程">
          <button v-for="(p, i) in projects" :key="p.id" role="tab" :aria-selected="current === i" :class="{ active: current === i }" @click="current = i">{{ p.name }}</button>
        </div>
        <div class="flow-stages" role="tabpanel" :aria-label="active.name + '流程'">
          <div v-for="(stage, i) in stages[current]" :key="stage" class="flow-stage">
            <div class="stage-marker">0{{ i + 1 }}</div><span>{{ stage }}</span><span class="stage-check" aria-hidden="true">↳</span>
          </div>
        </div>
        <div class="workbench-code"><div v-for="(line, i) in code[current]" :key="line"><span class="code-number">{{ i + 1 }}</span><code>{{ line }}</code></div></div>
        <div class="workbench-footer"><span><i></i> {{ active.name }} / 核心流程示意</span><a :href="withBase('/' + active.id + '/')">读懂这条链 <span aria-hidden="true">↗</span></a></div>
      </div>
    </section>

    <section class="course-metrics" aria-label="课程内容概览">
      <div><strong>{{ String(stats.projects).padStart(2, '0') }}<span> / 项目入口</span></strong><p>从采集工具到大模型训练与应用</p></div>
      <div><strong>{{ stats.sourceDocuments }}<span> / 讲义与参考原稿</span></strong><p>原理、源码与扩展阅读</p></div>
      <div><strong>10 min<span> / 框架速读</span></strong><p>快速建立 LLaMAFactory 与 LangChain 的地图</p></div>
    </section>

    <section id="projects" class="projects-section">
      <div class="section-heading"><div><div class="eyebrow">EXPLORE THE PROJECTS</div><h2>选择一条探索路线</h2></div><p>先看整体，再沿一条主线走进代码。</p></div>
      <div class="project-grid">
        <a v-for="(p, i) in projects" :key="p.id" :href="withBase('/' + p.id + '/')" :class="['project-card', p.id]">
          <div class="project-card-top"><div class="project-symbol" aria-hidden="true">
            <svg v-if="i === 0" viewBox="0 0 32 32" fill="none"><rect x="5" y="5" width="22" height="22" rx="5"/><path d="M5 12h22M11 8.5h.1M15 8.5h.1M12 17l-3 3 3 3M20 17l3 3-3 3M17 16l-2 8"/></svg>
            <svg v-else-if="i === 1" viewBox="0 0 32 32" fill="none"><rect x="9" y="9" width="14" height="14" rx="4"/><path d="M16 3v6M16 23v6M3 16h6M23 16h6M6 6l5 5M21 21l5 5M6 26l5-5M21 11l5-5"/><circle cx="16" cy="16" r="2"/></svg>
            <svg v-else-if="i === 2" viewBox="0 0 32 32" fill="none"><path d="M5 13l11-7 11 7-11 7-11-7Z M5 19l11 7 11-7M5 16l11 7 11-7"/></svg>
            <svg v-else-if="i === 3" viewBox="0 0 32 32" fill="none"><rect x="3" y="11" width="8" height="10" rx="3"/><rect x="21" y="11" width="8" height="10" rx="3"/><path d="M11 16h10M15 12l4 4-4 4"/></svg>
            <svg v-else viewBox="0 0 32 32" fill="none"><circle cx="7" cy="8" r="3"/><circle cx="7" cy="24" r="3"/><circle cx="25" cy="16" r="4"/><path d="M10 8l11 7M10 24l11-7M7 11v10"/></svg>
          </div><span class="project-format">{{ i === 2 || i === 3 ? '十分钟速读' : '系统剖析' }}</span><span class="card-arrow" aria-hidden="true">↗</span></div>
          <span class="project-eyebrow">{{ p.eyebrow }}</span><h3>{{ p.name }}</h3><p>{{ p.description }}</p>
          <div class="project-tags"><span v-for="tag in p.topics" :key="tag">{{ tag }}</span></div>
          <div class="project-card-footer">进入项目讲义 <span aria-hidden="true">→</span></div>
        </a>
      </div>
    </section>

    <footer class="course-home-footer"><span>开源软件分析与实践</span><span>真实项目 · 原理与实现 · 持续探索</span></footer>
  </main>
</template>
