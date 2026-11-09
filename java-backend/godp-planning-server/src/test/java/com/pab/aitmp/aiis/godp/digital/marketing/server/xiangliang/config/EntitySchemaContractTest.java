package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.config;

import static org.junit.jupiter.api.Assertions.*;
import com.baomidou.mybatisplus.annotation.*;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.BaseAudit;
import com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.dev.LocalManualBusinessSchema;
import java.lang.reflect.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

class EntitySchemaContractTest {
  @Test void everyBusinessTableHasExactlyOneTypedColumnMappingIncludingSixAuditFields() throws Exception {
    DriverManagerDataSource ds=new DriverManagerDataSource("jdbc:h2:mem:entity-"+UUID.randomUUID()
        +";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1","sa","");
    LocalManualBusinessSchema.initialize(ds);
    JdbcTemplate sql=new JdbcTemplate(ds);
    List<String> tables=sql.queryForList("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'",String.class);
    assertEquals(14,tables.size());
    for(String table:tables) {
      StringBuilder name=new StringBuilder();
      for(String part:table.substring(5).split("_")) name.append(Character.toUpperCase(part.charAt(0))).append(part.substring(1));
      Class<?> type=Class.forName("com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang."+name+"Entity");
      assertTrue(BaseAudit.class.isAssignableFrom(type));
      assertEquals(table,type.getAnnotation(TableName.class).value());
      Set<String> mapped=new HashSet<>();
      for(Field field:type.getFields()) {
        if(Modifier.isStatic(field.getModifiers())) continue;
        TableField column=field.getAnnotation(TableField.class);
        TableId id=field.getAnnotation(TableId.class);
        assertTrue(mapped.add(column!=null ? column.value():Objects.requireNonNull(id).value()));
      }
      assertEquals(new HashSet<>(sql.queryForList("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?",String.class,table)),mapped,table);
    }
  }
}
