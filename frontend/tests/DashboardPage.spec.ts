import { compileScript, compileTemplate, parse } from "@vue/compiler-sfc";
import * as Vue from "vue";
import { createRenderer, defineComponent, h, nextTick, ssrContextKey } from "vue";
import { createRouter, createMemoryHistory } from "vue-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "../src/pages/DashboardPage.vue";
import dashboardSource from "../src/pages/DashboardPage.vue?raw";

const apiState = vi.hoisted(() => ({
  getTaskStatus: vi.fn(async () => ({
    task_id: "TASK-1",
    status: "UPLOADED",
    auto_fixed_rows: 1,
    pending_ai_rows: 2,
    ai_processed_rows: 3,
    pending_human_rows: 4,
    unresolved_rows: 5,
  })),
  getTaskExceptions: vi.fn(async () => ({ task_id: "TASK-1", total: 0, items: [] })),
  startLiveReconciliation: vi.fn(async () => ({ task_id: "TASK-1", status: "AI_RUNNING" })),
}));

vi.mock("../src/api/reconcile", () => apiState);
vi.mock("../src/composables/useTaskEventStream", () => ({
  useTaskEventStream: () => ({
    events: { value: [] },
    progress: { value: null },
    status: { value: "idle" },
    error: { value: null },
    start: vi.fn(),
    abort: vi.fn(),
  }),
}));

interface TestNode {
  type: string;
  text: string;
  children: TestNode[];
  props: Record<string, unknown>;
  parent: TestNode | null;
}

const renderer = createRenderer<TestNode, TestNode>({
  createElement: (type) => ({ type, text: "", children: [], props: {}, parent: null }),
  createText: (text) => ({ type: "#text", text, children: [], props: {}, parent: null }),
  createComment: (text) => ({ type: "#comment", text, children: [], props: {}, parent: null }),
  setText: (node, text) => {
    node.text = text;
  },
  setElementText: (node, text) => {
    node.text = text;
  },
  parentNode: (node) => node.parent,
  nextSibling: (node) => {
    const siblings = node.parent?.children ?? [];
    return siblings[siblings.indexOf(node) + 1] ?? null;
  },
  insert: (child, parent, anchor = null) => {
    child.parent = parent;
    const index = anchor ? parent.children.indexOf(anchor) : -1;
    if (index >= 0) {
      parent.children.splice(index, 0, child);
      return;
    }
    parent.children.push(child);
  },
  remove: (child) => {
    const siblings = child.parent?.children;
    if (!siblings) {
      return;
    }
    const index = siblings.indexOf(child);
    if (index >= 0) {
      siblings.splice(index, 1);
    }
    child.parent = null;
  },
  patchProp: (node, key, _previousValue, nextValue) => {
    node.props[key] = nextValue;
  },
});

const DashboardPageForMount = {
  ...DashboardPage,
  setup(props: Record<string, unknown>, context: unknown) {
    const setupResult = DashboardPage.setup?.(props, context);
    if (!setupResult || typeof setupResult === "function") {
      return setupResult;
    }
    return {
      ...setupResult,
      BaseButton: buttonStub(),
      PageHeader: slotStub("header"),
      BaseCard: slotStub("section"),
      StatCard: statCardStub(),
      StatusBadge: {
        props: ["value"],
        render() {
          return h("span", this.value);
        },
      },
      BranchDistribution: slotStub("div"),
      EmptyState: slotStub("div"),
    };
  },
  render: compileDashboardRender(),
};

async function mountDashboard() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/tasks/:taskId", component: DashboardPageForMount }],
  });
  router.push("/tasks/TASK-1");
  await router.isReady();

  const root: TestNode = { type: "root", text: "", children: [], props: {}, parent: null };
  const app = renderer.createApp(DashboardPageForMount);
  app.use(router);
  app.provide(ssrContextKey, { modules: new Set() });
  app.mount(root);
  await flushPromises();
  return { root, app };
}

function compileDashboardRender() {
  const { descriptor } = parse(dashboardSource, { filename: "DashboardPage.vue" });
  if (!descriptor.scriptSetup || !descriptor.template) {
    throw new Error("DashboardPage.vue must keep script setup and template blocks");
  }
  const script = compileScript(descriptor, { id: "dashboard-page-test" });
  const compiled = compileTemplate({
    source: descriptor.template.content,
    filename: "DashboardPage.vue",
    id: "dashboard-page-test",
    bindingMetadata: script.bindings,
    compilerOptions: { bindingMetadata: script.bindings },
  });
  if (compiled.errors.length) {
    throw new Error(compiled.errors.map(String).join("\n"));
  }
  const code = compiled.code
    .replace(/^import \{([^}]+)\} from "vue"\n\n/, (_match, imports: string) => {
      const destructured = imports.replace(/\s+as\s+/g, ": ");
      return `const {${destructured}} = Vue;\n\n`;
    })
    .replace("export function render", "return function render");
  return new Function("Vue", code)(Vue);
}

function buttonStub() {
  return defineComponent({
    emits: ["click"],
    setup(_props, { emit, slots }) {
      return () => h("button", { onClick: () => emit("click") }, slots.default?.());
    },
  });
}

function slotStub(tag: string) {
  return defineComponent({
    setup(_props, { slots }) {
      return () => h(tag, [slots.default?.(), slots.actions?.()]);
    },
  });
}

function statCardStub() {
  return defineComponent({
    props: ["label", "value", "note"],
    setup(props) {
      return () => h("article", [h("span", props.label), h("strong", String(props.value))]);
    },
  });
}

async function flushPromises() {
  await Promise.resolve();
  await Promise.resolve();
  await nextTick();
}

function findButtonByText(root: TestNode, text: string): TestNode {
  const match = findNode(root, (node) => node.type === "button" && nodeText(node).includes(text));
  if (!match) {
    throw new Error(`Button not found: ${text}`);
  }
  return match;
}

function findNode(root: TestNode, predicate: (node: TestNode) => boolean): TestNode | null {
  if (predicate(root)) {
    return root;
  }
  for (const child of root.children) {
    const match = findNode(child, predicate);
    if (match) {
      return match;
    }
  }
  return null;
}

function nodeText(node: TestNode): string {
  return node.text + node.children.map(nodeText).join("");
}

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps manual refresh and wires audit start to the live task stream", async () => {
    const { root, app } = await mountDashboard();
    const text = nodeText(root);

    expect(apiState.getTaskStatus).toHaveBeenCalledWith("TASK-1");
    expect(apiState.getTaskExceptions).toHaveBeenCalledWith("TASK-1");
    expect(text).toContain("刷新");
    expect(text).toContain("自动修复");
    expect(text).toContain("1");
    expect(text).toContain("AI 已处理");
    expect(text).toContain("3");
    expect(text).toContain("待人工复核");
    expect(text).toContain("4");

    const startClick = findButtonByText(root, "启动 AI 审计").props.onClick;
    if (typeof startClick !== "function") {
      throw new Error("Start audit button is missing a click handler");
    }
    await startClick();
    await flushPromises();

    expect(apiState.startLiveReconciliation).toHaveBeenCalledWith("TASK-1");
    expect(apiState.getTaskStatus).toHaveBeenCalledWith("TASK-1");
    expect(apiState.getTaskExceptions).toHaveBeenCalledWith("TASK-1");

    app.unmount();
  });
});
