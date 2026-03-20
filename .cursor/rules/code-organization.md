# 代码组织规范

## 文件行数上限

- **Python 文件**：400 行（软上限，特殊情况可放宽至 500 行）
- **JavaScript 文件**：300 行（软上限）
- **超过上限必须拆分**，禁止使用 `if __name__ == "__main__"` 或注释折叠来规避

## 拆分的自然切分点

Python 文件超过 400 行时，按以下顺序优先拆分：

1. **类型定义** → `_types.py`（Pydantic model、dataclass、Enum）
2. **纯函数** → `_utils.py` 或 `_helpers.py`（无状态的工具函数）
3. **类方法** → 新类或 `_builder.py`（方法按职责分组）
4. **路由分发** → `_routes.py`（从 `app.py` 中提取）

## 包的结构规范

每个业务子包必须有 `__init__.py`，禁止裸模块（无 `__init__.py` 的目录）。

```
# 正确的包结构示例
atas_market_structure/
  my_feature/
    __init__.py          # 只写 from ._service import MyFeatureService
    _service.py          # 所有业务逻辑
    _types.py            # 请求/响应模型
    _router.py           # HTTP 路由（可选）
```

## 数据模型规范

- 所有 Pydantic model、dataclass、Enum 统一放在 `atas_market_structure/models/` 子包中
- 按领域分离：`models/_replay.py`、`models/_adapter.py`、`models/_market_structure.py` 等
- 禁止在 `models/` 以外的文件中定义数据模型

## 禁止的做法

- ❌ 把多个不相关的类塞进同一个文件
- ❌ 把 `XXXMixin`、`XXXBase` 作为逃避拆分的手段
- ❌ 在 `models.py` 中放除了数据类型以外的内容
- ❌ 单一文件超过 600 行（无论什么理由）
- ❌ 新功能直接写到已有的大文件中（必须创建新包或新文件）

## 新增功能的标准流程

```
第 1 步：在对应目录下创建 _types.py，写 Request/Response 模型
第 2 步：创建 _service.py，写业务逻辑类
第 3 步：在 __init__.py 中导入
第 4 步：在 app.py（或主路由文件）中注册路由
```

## 服务层单入口原则

每个业务域对应一个服务类，服务类的所有公共方法在 `_service.py` 中。

```
# 好的结构
atas_market_structure/
  my_feature/
    __init__.py
    _service.py          # MyFeatureService

# 坏的结构：往已有大文件里加新类
workbench_services.py   # ❌ 一直往里加新类
models.py               # ❌ 一直往里加新 model
```
