# ADF to Python Translation Rules

> Last updated: 2026-04-11

## Canonical Mapping Rules

These are the ground-truth mappings that the semantic equivalence judge uses. Any wkmigrate output that deviates from these is either a bug or a documented known gap.

### Rule 1: String functions always wrap in `str()`

wkmigrate convention: all string function arguments get explicit `str()` wrapping even for string literals. This handles the auto-coercion case uniformly.

```python
# @concat('a', 1) →
str('a') + str(1)  # NOT 'a' + str(1)

# @toUpper(pipeline().parameters.name) →
str(dbutils.widgets.get('name')).upper()
```

### Rule 2: Parameter references → dbutils.widgets.get()

```python
# @pipeline().parameters.X →
dbutils.widgets.get('X')

# In math context: @add(pipeline().parameters.count, 1) →
(int(dbutils.widgets.get('count')) + 1)
```

The coercion type depends on context:
- Math operations: `int(dbutils.widgets.get(...))` or `float(...)`
- String operations: `str(dbutils.widgets.get(...))` (usually no-op since already str)
- Boolean operations: `bool(dbutils.widgets.get(...))`

### Rule 3: Activity output references → task values or shared state

```python
# @activity('Lookup1').output.firstRow.config_value →
# In Databricks Jobs, this maps to task value passing:
dbutils.jobs.taskValues.get(taskKey='Lookup1', key='config_value')

# OR in notebook context:
spark.conf.get('pipeline.Lookup1.output.firstRow.config_value')
```

### Rule 4: Variables → notebook-scoped variables

```python
# @variables('myVar') →
# In wkmigrate's current translation:
variables['myVar']  # dict lookup
```

### Rule 5: Nested expressions preserve evaluation order

```python
# @concat(toUpper('x'), string(add(1, 2))) →
str(str('x').upper()) + str(str((1 + 2)))
# Evaluation: inner-to-outer, left-to-right
```

### Rule 6: ForEach items expressions → Python lists

```python
# @createArray(concat('a', pipeline().parameters.suffix), concat('b', pipeline().parameters.suffix)) →
[str('a') + str(dbutils.widgets.get('suffix')), str('b') + str(dbutils.widgets.get('suffix'))]
```

### Rule 7: IfCondition predicates → Python boolean expressions

```python
# @and(greater(pipeline().parameters.threshold, 50), not(equals(pipeline().parameters.env, 'prod'))) →
((int(dbutils.widgets.get('threshold')) > 50) and (not (dbutils.widgets.get('env') == 'prod')))
```

## Known Gaps (tracked via findings)

| Gap | ADF Pattern | Current wkmigrate Output | Expected | Finding |
|-----|-------------|-------------------------|----------|---------|
| ForEach items with expressions | `@createArray(concat(...))` | Placeholder notebook | Correct Python list | W-10 |
| Copy source sql_reader_query | Expression in source config | Silently dropped | Preserved in notebook | W-9 |
| Math on parameters without coercion | `@add(param, 1)` | `(param + 1)` (string concat!) | `(int(param) + 1)` | W-3 |
| Deep nesting (4+ levels) | `@if(equals(mod(len(split(...)),2),0),...)` | Often times out or errors | Correct nested Python | W-2 |

## Scoring Rubric for Semantic Equivalence

| Score | Meaning | Example |
|-------|---------|---------|
| 1.0 | Perfect semantic match | `str('x').upper()` for `@toUpper('x')` |
| 0.9 | Correct behavior, convention deviation | `'x'.upper()` (missing str() wrap) |
| 0.7-0.8 | Correct for common cases, edge case bug | `(a + b)` where a could be string |
| 0.5-0.6 | Partial — some logic preserved | Only first arg of multi-arg concat |
| 0.3-0.4 | Structural similarity only | Right function name, wrong arguments |
| 0.0-0.2 | Wrong or placeholder | `# TODO: translate expression` |
