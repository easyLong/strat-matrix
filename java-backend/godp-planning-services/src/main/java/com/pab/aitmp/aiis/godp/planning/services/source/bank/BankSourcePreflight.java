package com.pab.aitmp.aiis.godp.planning.services.source.bank;

import java.lang.reflect.*;
import java.time.*;
import java.util.*;
import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.ibatis.mapping.MappedStatement;

/** Validate every mapped SELECT before traffic. Resolves SQL only; never opens a DB connection. */
public final class BankSourcePreflight {
  private BankSourcePreflight() {}
  public static void verify(SqlSessionFactory factory) {
    for (Method method : BankSourceMapper.class.getDeclaredMethods()) {
      String id=BankSourceMapper.class.getName()+"."+method.getName();
      try {
        MappedStatement statement=factory.getConfiguration().getMappedStatement(id);
        Map<String,Object> values=new LinkedHashMap<>();
        for (Field field:method.getParameterTypes()[0].getFields()) {
          Class<?> type=field.getType();
          Object value=type==int.class ? 1 : type==long.class ? 0L
              : type==boolean.class ? true : type==Instant.class ? Instant.parse("2026-01-01T00:00:00Z")
              : type==LocalDate.class ? LocalDate.of(2026,1,1)
              : List.class.isAssignableFrom(type) ? Collections.singletonList("PREFLIGHT") : "PREFLIGHT";
          values.put(field.getName(),value);
        }
        String sql=statement.getBoundSql(Collections.singletonMap("query", values)).getSql().trim();
        if (sql.isEmpty() || !sql.toUpperCase(Locale.ROOT).matches("(?s)^(SELECT|WITH)\\b.*"))
          throw new IllegalStateException("missing read-only SELECT");
      } catch (RuntimeException invalid) {
        // Do not include SQL, source table names, credentials or underlying error text.
        throw new IllegalStateException("行内资料SQL未就绪："+method.getName());
      }
    }
  }
}
