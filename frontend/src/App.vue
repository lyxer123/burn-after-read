<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { createLinks, listLinks, shareLink, burnLink } from './api.js'

const file = ref(null)
const count = ref(1)
const recipient = ref('')
const watermark = ref('')
const keywords = ref('')
const generating = ref(false)
const message = ref('')

const links = ref([])
const loading = ref(false)

async function refresh() {
  loading.value = true
  try {
    const r = await listLinks()
    links.value = r.data.links
  } catch (e) {
    message.value = '加载失败: ' + (e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

async function onGenerate() {
  if (!file.value) {
    message.value = '请先选择要分享的文件'
    return
  }
  generating.value = true
  message.value = ''
  const fd = new FormData()
  fd.append('file', file.value)
  fd.append('count', String(count.value || 1))
  fd.append('recipient', recipient.value)
  fd.append('watermark_text', watermark.value)
  fd.append('keywords', keywords.value)
  try {
    const r = await createLinks(fd)
    message.value = `已生成 ${r.data.links.length} 个一次性链接`
    await refresh()
  } catch (e) {
    message.value = '生成失败: ' + (e.response?.data?.detail || e.message)
  } finally {
    generating.value = false
  }
}

async function copyLink(url) {
  try {
    await navigator.clipboard.writeText(url)
    await shareLink(url.split('/dl/')[1])
    message.value = '链接已复制并标记为已分享'
    await refresh()
  } catch (e) {
    message.value = '复制失败，请手动复制: ' + url
  }
}

async function burn(token) {
  if (!confirm('确定要召回（焚毁）该链接吗？对方将再也无法下载。')) return
  try {
    await burnLink(token)
    message.value = '链接已焚毁'
    await refresh()
  } catch (e) {
    message.value = '操作失败: ' + (e.response?.data?.detail || e.message)
  }
}

function statusBadge(l) {
  if (l.status === 'burned') {
    return l.downloaded_at
      ? { text: '已下载（已焚）', cls: 'badge red' }
      : { text: '已召回（已焚）', cls: 'badge purple' }
  }
  if (l.status === 'shared') return { text: '已分享', cls: 'badge blue' }
  if (l.status === 'downloaded') return { text: '已下载', cls: 'badge orange' }
  return { text: '已生成', cls: 'badge gray' }
}

function fmt(t) {
  if (!t) return '-'
  return t.replace('T', ' ').slice(0, 19)
}

let timer = null
onMounted(() => {
  refresh()
  timer = setInterval(refresh, 5000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="wrap">
    <header>
      <h1>onedl · 阅后即焚下载</h1>
      <p class="sub">生成一次性下载链接 · 可追踪是否已分享 / 下载 / 焚毁 · 支持自动水印</p>
    </header>

    <section class="card">
      <h2>生成链接</h2>
      <div class="form">
        <label>
          文件
          <input type="file" @change="e => file = e.target.files[0]" />
        </label>
        <label>
          数量
          <input type="number" min="1" v-model.number="count" />
        </label>
        <label>
          接收人（可选）
          <input type="text" v-model="recipient" placeholder="如 张三 / 微信号" />
        </label>
        <label class="wide">
          水印文字（可选，下载时自动打上）
          <input type="text" v-model="watermark" placeholder="如 发给:张三 2026-09-16" />
        </label>
        <label class="wide">
          微信关键词（可选，逗号分隔，如：白皮书,中压直挂充电白皮书）
          <input type="text" v-model="keywords" placeholder="用户公众号发这些词时自动匹配本文件" />
        </label>
        <button :disabled="generating" @click="onGenerate">
          {{ generating ? '生成中…' : '生成一次性链接' }}
        </button>
      </div>
    </section>

    <section class="card">
      <div class="table-head">
        <h2>链接状态</h2>
        <button class="ghost" :disabled="loading" @click="refresh">刷新</button>
      </div>
      <table>
        <thead>
          <tr>
            <th>文件</th>
            <th>接收人</th>
            <th>水印</th>
            <th>状态</th>
            <th>分享时间</th>
            <th>下载时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="l in links" :key="l.token">
            <td :title="l.original_name">{{ l.original_name }}</td>
            <td>{{ l.recipient || '-' }}</td>
            <td>{{ l.watermark_text || '-' }}</td>
            <td><span :class="statusBadge(l).cls">{{ statusBadge(l).text }}</span></td>
            <td>{{ fmt(l.shared_at) }}</td>
            <td>{{ fmt(l.downloaded_at) }}</td>
            <td class="ops">
              <button class="link" @click="copyLink('http://' + location.host + '/dl/' + l.token)">复制</button>
              <button class="link danger" v-if="l.status !== 'burned'" @click="burn(l.token)">焚毁</button>
            </td>
          </tr>
          <tr v-if="!links.length">
            <td colspan="7" class="empty">暂无链接</td>
          </tr>
        </tbody>
      </table>
    </section>

    <p class="msg" v-if="message">{{ message }}</p>
  </div>
</template>

<style>
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; background: #f5f6f8; color: #1f2329; }
.wrap { max-width: 1040px; margin: 0 auto; padding: 28px 20px 60px; }
header h1 { margin: 0 0 4px; font-size: 26px; }
.sub { margin: 0 0 18px; color: #6b7280; font-size: 14px; }
.card { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 18px 20px; margin-bottom: 18px; box-shadow: 0 1px 2px rgba(0,0,0,.03); }
.card h2 { margin: 0 0 14px; font-size: 17px; }
.form { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; align-items: end; }
.form label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: #4b5563; }
.form label.wide { grid-column: 1 / -1; }
.form input { padding: 8px 10px; border: 1px solid #d1d5db; border-radius: 8px; font-size: 14px; }
.form button { grid-column: 1 / -1; padding: 10px; border: 0; border-radius: 8px; background: #2563eb; color: #fff; font-size: 15px; cursor: pointer; }
.form button:disabled { opacity: .6; cursor: default; }
.table-head { display: flex; justify-content: space-between; align-items: center; }
.table-head h2 { margin: 0; }
.ghost { background: #eef2ff; color: #2563eb; border: 0; padding: 7px 14px; border-radius: 8px; cursor: pointer; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 9px 8px; border-bottom: 1px solid #f0f1f3; }
th { color: #6b7280; font-weight: 600; }
.empty { text-align: center; color: #9ca3af; padding: 24px; }
.ops { display: flex; gap: 8px; }
.link { background: none; border: 0; color: #2563eb; cursor: pointer; padding: 0; font-size: 13px; }
.link.danger { color: #dc2626; }
.badge { padding: 2px 9px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.badge.gray { background: #f3f4f6; color: #6b7280; }
.badge.blue { background: #dbeafe; color: #1d4ed8; }
.badge.orange { background: #ffedd5; color: #c2410c; }
.badge.red { background: #fee2e2; color: #b91c1c; }
.badge.purple { background: #f3e8ff; color: #7e22ce; }
.msg { color: #2563eb; font-size: 14px; }
</style>
