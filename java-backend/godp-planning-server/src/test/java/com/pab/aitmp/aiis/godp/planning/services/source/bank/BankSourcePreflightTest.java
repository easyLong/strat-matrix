package com.pab.aitmp.aiis.godp.planning.services.source.bank;

import static org.junit.jupiter.api.Assertions.*;
import java.io.InputStream;
import org.junit.jupiter.api.Test;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.*;
import org.apache.ibatis.session.*;
import org.apache.ibatis.builder.StaticSqlSource;
import org.springframework.core.io.ClassPathResource;

class BankSourcePreflightTest {
  @Test void placeholdersFailAtStartupWithoutEverOpeningADatabaseConnection() throws Exception {
    Configuration config=new Configuration();
    try(InputStream in=new ClassPathResource("bank-source/BankSourceMapper.xml").getInputStream()) {
      new XMLMapperBuilder(in,config,"bank-source/BankSourceMapper.xml",config.getSqlFragments()).parse();
    }
    assertThrows(IllegalStateException.class,() -> BankSourcePreflight.verify(new SqlSessionFactoryBuilder().build(config)));
  }
  @Test void allTenExplicitSelectsPassPreflightWithoutADatasource() {
    Configuration config=new Configuration();
    for(java.lang.reflect.Method method:BankSourceMapper.class.getDeclaredMethods()) {
      config.addMappedStatement(new MappedStatement.Builder(config,BankSourceMapper.class.getName()+"."+method.getName(),
          new StaticSqlSource(config,"SELECT 1"),SqlCommandType.SELECT).build());
    }
    assertDoesNotThrow(() -> BankSourcePreflight.verify(new SqlSessionFactoryBuilder().build(config)));
  }
  @Test void defaultUnimplementedServiceMethodsAreNotReportedAsReady() {
    assertThrows(IllegalStateException.class,() -> new BankSourceQueries() {}.verifyReady());
  }
}
