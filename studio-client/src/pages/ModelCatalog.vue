<template>
  <div class="catalog-page">
    <div class="page-header">
      <h2>模型目录</h2>
      <p class="subtitle">浏览可用模型 — 分类筛选与规格查询</p>
    </div>

    <div class="toolbar">
      <input v-model="search" placeholder="搜索模型..." class="search-input" @keyup.enter="fetchModels" />
      <select v-model="categoryFilter" class="select" @change="fetchModels">
        <option value="">全部分类</option>
        <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
      </select>
      <button class="btn btn-primary" @click="fetchModels">搜索</button>
      <button class="btn btn-outline" @click="fetchInfo">信息</button>
    </div>

    <div v-if="info" class="info-bar">
      <span>目录版本: {{ info.version }}</span>
      <span>模型集: {{ info.model_sets_count }}</span>
      <span>草稿: {{ info.draft_models_count }}</span>
      <span>更新于: {{ info.updated }}</span>
    </div>

    <div v-if="loading" class="loading">加载中...</div>

    <div v-else-if="models.length === 0" class="empty">暂无模型</div>

    <div v-else class="model-grid">
      <div v-for="m in models" :key="m.id" class="model-card" @click="selectModel(m)">
        <div class="card-header">
          <h4>{{ m.name }}</h4>
          <div class="categories">
            <span v-for="c in m.categories" :key="c" class="cat-tag">{{ c }}</span>
          </div>
        </div>
        <p v-if="m.description" class="desc">{{ m.description }}</p>
        <div class="specs">
          <div v-for="s in m.specs" :key="s.source_key" class="spec-row">
            <span class="spec-name">{{ s.name }}</span>
            <span class="spec-param">{{ s.parameter_count }}</span>
            <span class="spec-quants">{{ s.quantizations?.join(', ') }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="pagination" v-if="total > pageSize">
      <button class="btn btn-sm" :disabled="page <= 1" @click="page--; fetchModels()">上一页</button>
      <span class="page-info">{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
      <button class="btn btn-sm" :disabled="page * pageSize >= total" @click="page++; fetchModels()">下一页</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { catalogApi, type ModelSet, type CatalogInfo } from '@/api/catalog'

const models = ref<ModelSet[]>([])
const categories = ref<string[]>([])
const info = ref<CatalogInfo | null>(null)
const search = ref('')
const categoryFilter = ref('')
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)

async function fetchModels() {
  loading.value = true
  try {
    const res = await catalogApi.listModels({
      page: page.value,
      size: pageSize,
      category: categoryFilter.value || undefined,
      search: search.value || undefined,
    })
    models.value = res.data ?? []
    total.value = (res as any).total ?? 0
  } finally {
    loading.value = false
  }
}

async function fetchCategories() {
  try {
    const res = await catalogApi.listCategories()
    categories.value = (res as any)?.data ?? []
  } catch { /* ignore */ }
}

async function fetchInfo() {
  try {
    const res = await catalogApi.getInfo()
    info.value = res.data ?? res
  } catch { /* ignore */ }
}

async function selectModel(m: ModelSet) {
  try {
    const res = await catalogApi.getModel(m.id)
    alert(JSON.stringify(res.data ?? res, null, 2))
  } catch { /* ignore */ }
}

onMounted(() => {
  fetchModels()
  fetchCategories()
})
</script>

<style scoped>
.catalog-page { max-width: 1100px; margin: 0 auto; padding: 24px; }
.page-header h2 { margin: 0; font-size: 22px; }
.subtitle { color: var(--color-ide-text-secondary); margin: 4px 0 16px; font-size: 14px; }

.toolbar { display: flex; gap: 8px; margin-bottom: 16px; align-items: center; }
.search-input { flex: 1; padding: 6px 12px; border: 1px solid var(--color-ide-border); border-radius: 6px; background: var(--color-ide-bg-secondary); color: var(--color-ide-text-primary); }
.select { padding: 6px 12px; border: 1px solid var(--color-ide-border); border-radius: 6px; background: var(--color-ide-bg-secondary); color: var(--color-ide-text-primary); }

.info-bar { display: flex; gap: 20px; padding: 8px 16px; background: var(--color-ide-bg-secondary); border-radius: 8px; margin-bottom: 16px; font-size: 13px; color: var(--color-ide-text-secondary); }

.model-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }
.model-card { padding: 14px; border: 1px solid var(--color-ide-border); border-radius: 8px; background: var(--color-ide-bg-secondary); cursor: pointer; transition: border-color 0.15s; }
.model-card:hover { border-color: var(--color-ide-accent); }
.card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px; }
.card-header h4 { margin: 0; font-size: 15px; }
.categories { display: flex; gap: 4px; flex-wrap: wrap; }
.cat-tag { font-size: 10px; padding: 1px 6px; border-radius: 8px; background: var(--color-ide-bg-tertiary); color: var(--color-ide-text-secondary); }
.desc { font-size: 12px; color: var(--color-ide-text-secondary); margin: 4px 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.specs { margin-top: 8px; }
.spec-row { display: flex; gap: 12px; font-size: 12px; padding: 2px 0; color: var(--color-ide-text-secondary); }
.spec-name { font-weight: 600; min-width: 80px; }
.spec-param { min-width: 50px; }
.spec-quants { color: var(--color-ide-accent); }

.pagination { display: flex; justify-content: center; align-items: center; gap: 12px; margin-top: 20px; }
.page-info { font-size: 13px; color: var(--color-ide-text-secondary); }

.loading, .empty { text-align: center; padding: 40px; color: var(--color-ide-text-secondary); }

.btn { padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; background: var(--color-ide-bg-tertiary); color: var(--color-ide-text-primary); transition: opacity 0.15s; }
.btn:hover { opacity: 0.85; }
.btn-primary { background: var(--color-ide-accent); color: #fff; }
.btn-outline { border: 1px solid var(--color-ide-border); background: transparent; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
