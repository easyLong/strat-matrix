package com.stratmatrix.planning.source.bank;

import static com.stratmatrix.planning.source.bank.BankSourceValues.invalid;

import java.util.*;

/** Optional site mappings. No guessed columns/codes, reflection, expressions or SQL generation. */
public final class BankSourceFieldRules {
  private final Map<String, String> aliases;
  private final Map<String, Map<String, Object>> codes;

  private BankSourceFieldRules(Builder builder) {
    aliases = Collections.unmodifiableMap(new LinkedHashMap<>(builder.aliases));
    Map<String, Map<String, Object>> copied = new LinkedHashMap<>();
    builder.codes.forEach(
        (field, values) ->
            copied.put(field, Collections.unmodifiableMap(new LinkedHashMap<>(values))));
    codes = Collections.unmodifiableMap(copied);
  }

  public static Builder builder() {
    return new Builder();
  }

  public static BankSourceFieldRules none() {
    return builder().build();
  }

  Object read(BankSourceMapping.Kind kind, Map<String, Object> row, String field, String chinese) {
    Object value = BankSourceValues.value(row, field, chinese, 502);
    String key = key(kind, field), column = aliases.get(key);
    if (column != null && row.containsKey(column)) {
      if ((row.containsKey(field) || row.containsKey(chinese))
          && !Objects.deepEquals(value, row.get(column)))
        throw invalid(502, kind + "." + field + "字段映射冲突");
      value = row.get(column);
    }
    Map<String, Object> translation = codes.get(key);
    if (value != null && translation != null) {
      if (!translation.containsKey(value.toString()))
        throw invalid(502, kind + "." + field + "含未映射编码");
      value = translation.get(value.toString());
    }
    return value;
  }

  void removeAlias(BankSourceMapping.Kind kind, String field, Map<String, Object> row) {
    String alias = aliases.get(key(kind, field));
    if (alias != null) row.remove(alias);
  }

  private static String key(BankSourceMapping.Kind kind, String field) {
    return Objects.requireNonNull(kind).name() + "." + field;
  }

  public static final class Builder {
    private final Map<String, String> aliases = new LinkedHashMap<>();
    private final Map<String, Map<String, Object>> codes = new LinkedHashMap<>();

    private Builder() {}

    private String field(BankSourceMapping.Kind kind, String field) {
      if (!BankSourceMapping.fieldNames(kind).contains(field))
        throw new IllegalArgumentException("未约定的资料映射字段");
      return key(kind, field);
    }

    public Builder alias(BankSourceMapping.Kind kind, String field, String sourceColumn) {
      String key = field(kind, field);
      if (sourceColumn == null
          || sourceColumn.trim().isEmpty()
          || !sourceColumn.equals(sourceColumn.trim()))
        throw new IllegalArgumentException("资料列名不能为空或包含首尾空格");
      String owner = BankSourceMapping.canonicalField(kind, sourceColumn);
      if (owner != null && !owner.equals(field))
        throw new IllegalArgumentException("资料列名与已有契约字段冲突");
      for (Map.Entry<String, String> existing : aliases.entrySet())
        if (existing.getKey().startsWith(kind.name() + ".")
            && !existing.getKey().equals(key)
            && existing.getValue().equals(sourceColumn))
          throw new IllegalArgumentException("同一资料列不能映射到多个字段");
      if (aliases.containsKey(key)) throw new IllegalArgumentException("资料字段映射重复定义");
      aliases.put(key, sourceColumn);
      return this;
    }

    public Builder code(
        BankSourceMapping.Kind kind, String field, Object sourceCode, Object canonicalValue) {
      String key = field(kind, field);
      if (!scalar(sourceCode) || !scalar(canonicalValue))
        throw new IllegalArgumentException("编码映射只接受非空文本、布尔或数值");
      Map<String, Object> values = codes.computeIfAbsent(key, ignored -> new LinkedHashMap<>());
      if (values.containsKey(sourceCode.toString()))
        throw new IllegalArgumentException("资料编码映射重复定义");
      values.put(sourceCode.toString(), canonicalValue);
      return this;
    }

    private boolean scalar(Object value) {
      return value instanceof String || value instanceof Boolean || value instanceof Number;
    }

    public BankSourceFieldRules build() {
      return new BankSourceFieldRules(this);
    }
  }
}
