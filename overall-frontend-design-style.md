# Overall Frontend Design Style

> 设计参考：Claude.ai / Anthropic 系产品的界面气质。目标不是复制品牌资产，而是提炼其“温和、克制、清晰、可信、以文字和任务为中心”的前端体验，用于项目的统一视觉与交互规范。

## 1. 设计关键词

整体风格应保持：安静、克制、理性、温暖、留白充分、文字友好、低装饰、高可读性。

界面不追求强烈科技感，也不使用高饱和渐变、霓虹、玻璃拟态、夸张阴影或复杂动效。视觉重心应放在内容、输入、对话、任务流和清晰的操作反馈上。

用户看到界面时，应感受到：这是一个稳定、可信、专业、但不冰冷的产品。

## 2. 视觉原则

### 2.1 内容优先

所有布局都应服务于阅读、理解和操作。页面不要为了“丰富”而增加多余卡片、图标、背景纹理或装饰性组件。

优先保证：

- 文字层级清楚
- 操作入口明确
- 页面留白充足
- 信息密度适中
- 当前任务路径可被快速理解

### 2.2 温暖的中性色系统

整体色彩基调使用偏暖的中性色，而不是纯白、纯黑或偏蓝灰的企业 SaaS 风格。

推荐基调：

```css
:root {
  --color-bg: #f7f3ec;
  --color-bg-soft: #fbf8f2;
  --color-surface: #fffdf8;
  --color-surface-muted: #f1ece3;

  --color-text: #2b2926;
  --color-text-muted: #6f6a61;
  --color-text-subtle: #9a9286;

  --color-border: #ded6c8;
  --color-border-soft: #ebe4d8;

  --color-accent: #c96442;
  --color-accent-hover: #b45537;
  --color-accent-soft: #f0d7c9;

  --color-success: #587c55;
  --color-warning: #b9822f;
  --color-danger: #b75b51;
  --color-info: #5f7896;
}
```

使用规则：

- 主背景避免 `#ffffff`，使用轻微暖色底。
- 文本避免纯黑，使用接近炭黑的暖黑。
- 分割线和边框应低对比度。
- 强调色只用于主按钮、当前状态、焦点态和少量高价值提示。
- 不使用大面积品牌色铺底。

### 2.3 克制的层次感

Claude.ai 风格的界面层次通常不是靠强阴影，而是靠留白、边框、背景色差和排版建立。

推荐：

```css
.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border-soft);
  border-radius: 16px;
  box-shadow: 0 1px 2px rgba(43, 41, 38, 0.04);
}
```

避免：

```css
/* 不推荐 */
box-shadow: 0 20px 60px rgba(0, 0, 0, 0.18);
background: linear-gradient(135deg, #7c3aed, #2563eb);
backdrop-filter: blur(24px);
```

## 3. 排版系统

### 3.1 字体方向

界面应呈现“编辑器 + 文档”的质感，而不是营销页或游戏化工具。

推荐字体栈：

```css
:root {
  --font-sans: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-serif: Georgia, "Times New Roman", "Songti SC", serif;
  --font-mono: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}
```

使用规则：

- 产品 UI 主体使用 sans-serif。
- 长文、说明、空状态文案可以少量使用 serif，增加温和的人文感。
- 代码、命令、变量、token 使用 mono。
- 不使用过度圆润、娱乐化或强品牌感字体。

### 3.2 字号与行高

```css
:root {
  --text-xs: 12px;
  --text-sm: 14px;
  --text-md: 16px;
  --text-lg: 18px;
  --text-xl: 22px;
  --text-2xl: 28px;

  --leading-tight: 1.25;
  --leading-normal: 1.5;
  --leading-relaxed: 1.7;
}
```

建议：

- 正文默认 `16px / 1.5`。
- 说明文字 `14px / 1.5`。
- 长文阅读区域可使用 `16px / 1.7`。
- 标题不要过大，避免营销化。
- 字重优先使用 400、500、600，少用 700 以上。

## 4. 布局规范

### 4.1 页面结构

页面布局应稳定、可预测。推荐采用以下结构：

```text
App Shell
├── Sidebar / Navigation
├── Main Content
│   ├── Page Header
│   ├── Primary Work Area
│   └── Contextual Panels / Cards
└── Optional Composer / Input Area
```

布局原则：

- 左侧导航保持窄、安静、低对比度。
- 主内容区居中，最大宽度受控。
- 页面顶部只放当前任务相关信息。
- 右侧面板只在确实有上下文信息时出现。

推荐尺寸：

```css
:root {
  --sidebar-width: 280px;
  --content-max-width: 960px;
  --content-wide-max-width: 1200px;
  --page-padding: 24px;
  --page-padding-lg: 40px;
}
```

### 4.2 间距系统

使用 4px 基础栅格，保证界面节奏统一。

```css
:root {
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
}
```

使用规则：

- 卡片内边距通常为 16px、20px 或 24px。
- 页面主区域左右留白不小于 24px。
- 相关元素间距小，不相关模块间距大。
- 避免所有元素等距排列。

## 5. 圆角与边框

Claude.ai 风格偏柔和，但不是儿童化圆角。

```css
:root {
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 22px;
  --radius-full: 999px;
}
```

使用规则：

- 按钮、输入框：10px–14px。
- 卡片、面板：14px–18px。
- 大型输入容器：18px–24px。
- 不使用过度胶囊化的主界面容器，除非是标签、状态或小按钮。

## 6. 组件风格

### 6.1 按钮

按钮应安静、明确。主按钮只用于页面主动作。

```css
.button-primary {
  background: var(--color-text);
  color: var(--color-bg-soft);
  border: 1px solid var(--color-text);
  border-radius: 12px;
  padding: 10px 16px;
  font-size: 14px;
  font-weight: 500;
}

.button-secondary {
  background: transparent;
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 10px 16px;
  font-size: 14px;
  font-weight: 500;
}

.button-ghost {
  background: transparent;
  color: var(--color-text-muted);
  border: 1px solid transparent;
  border-radius: 10px;
  padding: 8px 12px;
}
```

按钮状态：

- hover：轻微加深背景或边框。
- active：轻微内收或背景加深。
- disabled：降低透明度，不改变布局。
- loading：保留按钮宽度，显示简洁 loading 状态。

### 6.2 输入框

输入框是产品体验的核心组件，应舒适、稳定、低干扰。

```css
.input,
.textarea {
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: 14px;
  padding: 12px 14px;
  font-size: 15px;
  line-height: 1.5;
  outline: none;
}

.input:focus,
.textarea:focus {
  border-color: var(--color-text-muted);
  box-shadow: 0 0 0 3px rgba(43, 41, 38, 0.08);
}
```

原则：

- placeholder 文案要短，不要像广告语。
- 聚焦态清楚但不刺眼。
- 输入区域可适度放大，给用户“正在创作”的空间。

### 6.3 卡片

卡片用于承载独立信息块，不用于制造视觉噪音。

```css
.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
}
```

卡片内部应有明确的信息层级：标题、说明、主体、操作。不要在一个卡片里堆太多按钮。

### 6.4 导航

导航区域应低存在感，帮助用户定位，不抢主内容注意力。

```css
.nav-item {
  color: var(--color-text-muted);
  border-radius: 10px;
  padding: 8px 10px;
  font-size: 14px;
}

.nav-item:hover {
  background: var(--color-surface-muted);
  color: var(--color-text);
}

.nav-item[data-active="true"] {
  background: var(--color-surface-muted);
  color: var(--color-text);
  font-weight: 500;
}
```

### 6.5 对话 / 消息气泡

如果项目包含 AI、聊天、评论或协作界面，消息样式应接近文档阅读体验，而不是社交聊天气泡。

推荐：

- 用户输入可以使用轻微背景块区分。
- 系统/助手回复优先使用自然文本流。
- 长回复使用段落、代码块、表格和引用块建立结构。
- 不使用强烈左右气泡对撞布局。

```css
.message-user {
  background: var(--color-surface);
  border: 1px solid var(--color-border-soft);
  border-radius: 18px;
  padding: 14px 16px;
}

.message-assistant {
  color: var(--color-text);
  line-height: var(--leading-relaxed);
}
```

## 7. 图标与插图

图标应线性、简洁、低对比度。

规则：

- 图标尺寸常用 16px、18px、20px。
- stroke 宽度保持 1.5–2px。
- 图标不承担主要表达，必须有文字标签或 tooltip。
- 插图少用，且应偏手工、温和、抽象，不用 3D 卡通或高饱和科技插画。

## 8. 动效规范

动效应帮助用户理解状态变化，不制造表演感。

```css
:root {
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
  --duration-fast: 120ms;
  --duration-normal: 180ms;
  --duration-slow: 260ms;
}
```

使用场景：

- hover / focus：120–180ms。
- panel 展开收起：180–260ms。
- toast 出现：180ms 左右。
- 页面切换：尽量轻，不使用大幅位移。

避免：

- 弹跳动画。
- 过长 loading 动画。
- 大面积视差滚动。
- 不必要的 hover 炫技。

## 9. 状态反馈

状态反馈应明确但克制。

### 9.1 Loading

优先使用 skeleton、淡入占位或小型 spinner。不要使用全屏 loading，除非页面确实无法局部加载。

### 9.2 Empty State

空状态文案应直接说明当前没有什么，以及用户下一步能做什么。

示例：

```text
还没有项目
创建一个项目后，它会显示在这里。
```

不要写成：

```text
释放你的创造力，开启无限可能！
```

### 9.3 Error State

错误提示要具体、可操作。

示例：

```text
保存失败。请检查网络连接后重试。
```

不要写成：

```text
出了点问题。
```

除非系统确实无法判断原因。

## 10. 文案风格

文案应平实、简短、具体。避免营销腔、夸张语和过度拟人化。

推荐语气：

- “创建项目”
- “上传文件”
- “保存更改”
- “未找到匹配结果”
- “需要先选择一个数据源”

避免语气：

- “让我们开始奇妙旅程”
- “一键释放生产力”
- “探索无限可能”
- “智能赋能全链路体验”

## 11. 深色模式

深色模式不应是纯黑，而应保持温暖、低对比、适合长时间阅读。

```css
[data-theme="dark"] {
  --color-bg: #1f1d1a;
  --color-bg-soft: #26231f;
  --color-surface: #2d2924;
  --color-surface-muted: #38332c;

  --color-text: #ede7dc;
  --color-text-muted: #b8afa2;
  --color-text-subtle: #8f867a;

  --color-border: #494238;
  --color-border-soft: #3d372f;

  --color-accent: #d48767;
  --color-accent-hover: #e0997a;
  --color-accent-soft: #4a3028;
}
```

深色模式规则：

- 避免纯黑背景。
- 避免高亮白色文本大面积使用。
- 边框应比背景略亮，但不要明显发光。
- 强调色降低饱和度，保持舒适。

## 12. 响应式设计

### 12.1 桌面端

桌面端适合采用 sidebar + main content。主内容不要无限拉宽，长文阅读区最大宽度建议 720px–860px。

### 12.2 平板端

侧边栏可以收窄为 icon + label，或转为顶部导航。上下文面板应默认折叠。

### 12.3 移动端

移动端重点是输入和阅读：

- 页面左右 padding 16px。
- 卡片圆角可略小。
- 侧边栏改为 drawer。
- 主操作固定在底部时，需要避免遮挡输入区域。
- 表格必须转为卡片或横向滚动。

## 13. 可访问性

必须满足基本可访问性要求：

- 正文文本与背景对比度不低于 WCAG AA。
- 所有可交互元素必须有清晰 focus 状态。
- 不只用颜色表达状态。
- icon-only 按钮必须有 aria-label。
- 表单错误必须绑定到对应输入项。
- 动效应尊重 `prefers-reduced-motion`。

```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
}
```

## 14. 禁止项

不要使用以下视觉模式：

- 大面积紫蓝渐变。
- 玻璃拟态卡片堆叠。
- 霓虹描边和发光按钮。
- 过度圆润的儿童化组件。
- 复杂背景网格、粒子、波浪装饰。
- 每个模块都加阴影。
- 过多 emoji。
- 夸张插画和 3D 吉祥物。
- 营销页式大标题和口号。
- 无意义的 AI 感装饰，如魔法棒、星星、闪光背景。

## 15. Tailwind Token 建议

如果项目使用 Tailwind，可以将风格抽象为如下 token：

```js
export const theme = {
  colors: {
    bg: "#f7f3ec",
    bgSoft: "#fbf8f2",
    surface: "#fffdf8",
    surfaceMuted: "#f1ece3",
    text: "#2b2926",
    textMuted: "#6f6a61",
    textSubtle: "#9a9286",
    border: "#ded6c8",
    borderSoft: "#ebe4d8",
    accent: "#c96442",
    accentHover: "#b45537",
    accentSoft: "#f0d7c9"
  },
  borderRadius: {
    sm: "8px",
    md: "12px",
    lg: "16px",
    xl: "22px"
  },
  boxShadow: {
    soft: "0 1px 2px rgba(43, 41, 38, 0.04)",
    panel: "0 8px 24px rgba(43, 41, 38, 0.06)"
  }
}
```

## 16. 实现检查清单

每个页面完成后，用以下标准检查：

- 页面是否以内容和任务为中心，而不是以装饰为中心？
- 是否使用了统一的暖中性色背景？
- 主按钮是否只有一个明确主动作？
- 字号、行高、间距是否稳定？
- 卡片是否靠边框和留白建立层次，而不是靠重阴影？
- 文案是否简短、具体、无营销腔？
- hover、focus、loading、empty、error 状态是否完整？
- 移动端是否仍然易读、易操作？
- 深色模式是否舒适，而不是简单反色？
- 是否避免了常见的“AI 生成感”视觉套路？

## 17. 一句话方向

界面应像一个安静、可靠、排版良好的工作台：温暖但不花哨，专业但不冷漠，重点始终放在用户正在处理的内容和任务上。

## 参考来源

- Anthropic 官方介绍 Claude Design：强调通过设计系统保持输出一致，并支持原型、线框、视觉探索和品牌化产出。
- Geist 对 Anthropic 品牌与产品 UI 的案例说明：强调温暖色彩系统、技术精炼但有人文气质的排版，以及 function-first 的 UI component system。
- Anthropic Claude Cookbook 的 frontend aesthetics 指南：强调明确约束 typography、color、motion、background，避免通用、保守、模板化的 AI 生成视觉。
