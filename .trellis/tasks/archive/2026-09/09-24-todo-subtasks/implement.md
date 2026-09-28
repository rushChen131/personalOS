# todo-subtasks 执行记录

## 背景

用户要求：**todolist 里单条待办可以嵌套一层 todolist**。四条口径由用户当场确认（见 `prd.md`）：

| # | 问题 | 结论 |
|---|---|---|
| D1 | 父子完成状态 | **互相独立**，父自己勾 |
| D2 | dashboard 展示 | **只列顶层**，点击展开子条目 |
| D3 | 子条目字段 | **只填标题**，分类/日期继承父条目 |
| D4 | 删除父条目 | **级联删掉子条目** |

形态：`todos` 加一个自引用 `parent_id`。`NULL` = 顶层；有值 = 某条的「步骤」。
深度**只有一层**——两层以上就不是清单而是项目树了，而 `Project` 已经退役。

## Step 1. 模型 `app/models/project.py`

- `Todo.parent_id: Mapped[str | None] = mapped_column(ForeignKey("todos.id", ondelete="CASCADE"), nullable=True)`
- `Todo.children` / `Todo.parent` 自引用关系；`children` 带 `cascade="all, delete-orphan"`。
- `children` 用 `order_by="Todo.created_at"` —— 顶层列表是「未完成在前、新的在前」，
  但步骤如果跟着重排，勾一个就跳一次，清单会散架。
- 新索引 `idx_todos_parent`。

**深度不在 schema 里**：SQLite 无法表达可移植的自引用 `CHECK`，规则放在 `TodoService.create`。

### ⚠️ `ondelete="CASCADE"` 单独不够

后端**从不发 `PRAGMA foreign_keys=ON`**，SQLite 默认外键 **OFF**，所以批量 `DELETE`
根本不会级联。只靠 FK 会留下一批 `parent_id` 悬空的子行；而 `GET /todos` 只读顶层，
这些孤儿**看不见但仍然占行**。因此 `TodoRepository.delete()` **显式**删子行，FK 只作为
PostgreSQL 下的第二道防线。

## Step 2. 迁移 `20260924_0005_todo_subtasks.py`

`down_revision = "20260924_0004"`。

- SQLite 下 `op.add_column` 带 `ForeignKey` 会抛
  `NotImplementedError: No support for ALTER of constraints`，**必须用 `op.batch_alter_table`**。
- batch 模式会**重建表**，所以**每个约束都必须有名字**：匿名 FK 直接
  `ValueError: Constraint must have a name`。这里命名 `fk_todos_parent_id_todos`。
- `upgrade()` / `downgrade()` 都用 `sa.inspect` 先探列/索引再动，幂等。

**踩过的坑（假成功）**：`20260924_0004` 是用 `Todo.__table__.create(bind, checkfirst=True)`
从**当前元数据**建表的，而当前元数据**已经含 `parent_id`**。所以在一个「0004 刚跑完」的
库上跑 0005，探测发现列已存在 → 跳过 → 看起来通过，其实什么都没验证。
判据：`alembic check` 会报 `Target database is not up to date`。
**每次都要用全新副本重测**，不能在已被 0004 重建过的库上测。

## Step 3. schema / repository / service / API

- `TodoCreate` 加 `parent_id: str | None`；`TodoUpdate` **刻意不加**（改父级不在范围内）。
- `TodoResponse` 加 `parent_id` + `children: list[TodoResponse]`（自引用，已验证能解析）。
- `TodoRepository`：
  - 保留扁平 `list()`（报表 / insight 引擎要的就是扁平集）。
  - 新增 `list_tree()`：`parent_id IS NULL` + `selectinload(Todo.children)`。
    `completed` / `category` **过滤父行**——子条目有自己的完成态，用它过滤会让父行
    忽隐忽现；分页也按父行计，所以一页可能装下超过 page size 的 todo。
  - `delete()` 显式先删子行再删父行。
- `TodoService.create()`：校验父存在（否则 404，也覆盖了别人的 todo——答 404 而不是 403，
  避免确认该 id 存在）→ 父本身是子条目则 400 → 子条目 `category` / `target_date`
  从父复制，**调用方传的值被忽略**。
- `TodoService.update()`：`todo.parent_id is not None` 时 `fields.pop("category")` /
  `fields.pop("target_date")`，写路径和读路径同一条规则。
- `TodoAPI._to_response(todo, children=())`：**children 显式传参**，不从 `todo.children` 读。
  未 eager-load 的关系在 asyncio 下会抛 `MissingGreenlet`，传参就从根上堵住了。

## Step 4. AI 层

- `tools/registry.py::_run_query_todos`：只查顶层 + `selectinload(children)`，
  返回 `{**as_item(row), "steps": [...]}`。子条目**不作为独立条目上报**，否则模型会
  把它当成一件独立的事来回答。
- `ai/context.py`：`_todo_block` 加 `parent_id` + `steps`，新增 `_steps()`，
  `_todos()` 改成「顶层 + 步骤」。

## Step 5. 前端 `dashboard/page.tsx`

- `types/api.ts`：`Todo` 加 `parent_id` / `children`，`TodoCreate` 加 `parent_id`。
- 只有 `children.length > 0` 的行才渲染折叠控件（▸ + `done/total`），
  `aria-expanded` + `aria-label` 跟随展开态。
- 展开后步骤缩进一层，**各自独立复选框**，**不显示分类/日期徽章**——那正是 D3 的意思。
- 每行一个 `+` 打开**只填标题**的行内表单，下面一行灰字说明「分类与截止日期继承自父条目」。
- 步骤表单用**第二个 `useCreateTodo()` 实例**：行内表单和弹窗共用一个 mutation 的话，
  步骤创建失败会把错误渲染进新建待办弹窗里（反之亦然）。
- **删除要两下**：有子条目的父行第一次点击只是「上膛」（按钮变成
  `确认删除（含 N 个步骤）`），第二下才真删；没有子条目的行保持原来一下即删。
  级联删除是这次新引入的破坏性行为，静默删掉 5 个步骤太容易误触。
- i18n：`todos.steps` / `expand` / `collapse` / `addStep` / `newStep` / `stepPlaceholder` /
  `inheritHint` / `errorCreateStep` / `confirmDeleteSteps`，**zh 与 en 同步加**。

## Step 6. 测试与门禁

- `tests/test_smoke.py::NestedTodoTest`：8 个用例覆盖 AC1–AC7
  （继承、深度上限 400、跨用户 404、树形、完成态互不影响、级联删除、过滤只作用于父行、
  继承字段不可改）。
- `tests/test_ai_layer.py`：`test_todo_page_context_includes_related_blocks` 加 `steps` 断言；
  新增 `test_query_todos_reports_steps_under_their_parent`（AC10）。
- `scripts/smoke_test.py`：新增 `[todo subtasks]` 段，14 项。

### ⚠️ 原始 SQL 断言的两个陷阱

1. **`Uuid` 列在 SQLite 上存的是 32 位无横线 hex**，而 API 返回 36 位带横线 UUID。
   `WHERE id = ?` 直接拿 API 的值去查**永远查不到**，于是
   `assertEqual(count, 0)` 之类的断言**空过**（看着绿，其实什么都没验证）。
   测试里统一走 `_row_id(api_id) = api_id.replace("-", "")`。
2. **空过必须用反向对照证明**：临时把 `TodoRepository.delete()` 里的子行删除注掉，
   用例必须失败（实测 `2 != 0`），否则无法区分「真通过」和「查错了库/查错了 id」。

## 验证结果

| 项 | 结果 |
|---|---|
| `ruff check app/ tests/ scripts/` | All checks passed |
| `unittest discover -s tests` | **80 OK**（原 71） |
| `scripts/smoke_test.py` | **83 PASSED / 0 FAILED**（原 69） |
| `alembic current` / `upgrade head` / `check` | `20260924_0005 (head)` / no-op / `No new upgrade operations detected` |
| `tsc --noEmit` / `next lint` | 干净 |
| i18n zh/en 键数 | 176 × 2，无单侧残留 |
| 活体探针（后端直连，`probe_nesting.py`） | **20 PASSED / 0 FAILED** |
| 活体探针（前端代理 `/api/backend/*`，`probe_proxy_nesting.py`） | **14 PASSED / 0 FAILED** |

## 调试过程中真正踩到的坑

1. **探针自己写错了**：`call(method, path, body=None, token=None)` 被写成
   `call("DELETE", path, token)` —— token 落进了 `body`，于是 `401 Missing bearer token`。
   一度以为是级联删除坏了，其实是**测试脚本**的问题。教训：断言失败先看**响应体**，
   别急着改实现。
2. **`--reload` 会静默卡住**：日志出现 `WatchFiles detected changes … Reloading…`
   之后**没有** `Application startup complete.`，worker 继续跑旧代码。
   判断依据是日志行，**不是 PID**。本次会话发生两次。
3. **活体探针必须先确认拿到响应体**，`status, _ = call(...)` 这种丢弃 body 的写法
   会把「401」和「500」都显示成一句 `FAIL`，白丢一轮。

## 未做 / 待跟进

- **不 `git commit`**（用户口径：实现即可，提交我自己来）。
- `CopilotPanel.tsx:182` 用了 `text-danger`，但 `tailwind.config.ts` **没有 `danger` 颜色**
  （`globals.css` 也没有 `--danger`），所以这个类**不生成任何样式**，错误文字一直是默认色。
  属于既有隐患，与本次改动无关，未擅自改（加颜色令牌是设计决定）。
- 报表 / insight 引擎仍走扁平查询，子条目是真实行所以不丢数据；要嵌套是另一件事。
