<template>
  <div class="stn-node">
    <div
      class="stn-node__label"
      :style="{ paddingLeft: (node.level - 1) * 20 + 8 + 'px' }"
    >
      <span v-if="node.children && node.children.length > 0" class="stn-node__toggle" @click="toggle">
        {{ open ? '▾' : '▸' }}
      </span>
      <span v-else class="stn-node__toggle stn-node__toggle--empty" />
      <span class="stn-node__text" :class="`stn-node__text--h${node.level}`">
        {{ node.text }}
      </span>
    </div>
    <div v-if="open && node.children && node.children.length" class="stn-node__children">
      <StructureTreeNode
        v-for="(child, i) in node.children"
        :key="i"
        :node="child"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import type { StructureNode } from "@/api/rag"

defineProps<{ node: StructureNode }>()

const open = ref(true)

function toggle() {
  open.value = !open.value
}
</script>

<style scoped>
.stn-node {
  font-size: 13px;
  line-height: 1.6;
}
.stn-node__label {
  display: flex;
  align-items: center;
  padding: 3px 0;
  cursor: default;
  border-radius: 4px;
  transition: background 0.15s;
}
.stn-node__label:hover {
  background: var(--color-ide-hover, rgba(255,255,255,0.05));
}
.stn-node__toggle {
  width: 16px;
  flex-shrink: 0;
  text-align: center;
  color: var(--color-ide-text-secondary, #888);
  cursor: pointer;
  user-select: none;
  font-size: 11px;
}
.stn-node__toggle--empty {
  cursor: default;
}
.stn-node__text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.stn-node__text--h1 { font-weight: 700; color: var(--color-ide-text-primary, #e0e0e0); }
.stn-node__text--h2 { font-weight: 600; color: var(--color-ide-text-primary, #d0d0d0); }
.stn-node__text--h3 { font-weight: 500; }
.stn-node__text--h4 { font-weight: 400; font-size: 12px; }
.stn-node__text--h5,
.stn-node__text--h6 { font-weight: 400; font-size: 12px; color: var(--color-ide-text-secondary, #888); }
.stn-node__children {
  /* nested */
}
</style>
