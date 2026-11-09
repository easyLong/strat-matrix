package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.config;

import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.ManualMapper;
import java.io.InputStream;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;

import static org.junit.jupiter.api.Assertions.*;

class VendorMapperIsolationTest {
  @Test
  void identicalFileAndStatementNamesRemainIsolatedByVendorNamespace() throws Exception {
    Configuration configuration = new Configuration();
    for (String resource : new String[] {
        "mapper/xiangliang/ManualMapper.xml", "other-vendor/ManualMapper.xml"}) {
      try (InputStream in = new ClassPathResource(resource).getInputStream()) {
        new XMLMapperBuilder(in, configuration, resource, configuration.getSqlFragments()).parse();
      }
    }
    assertTrue(configuration.hasMapper(ManualMapper.class));
    assertEquals("SELECT 1", configuration.getMappedStatement(ManualMapper.class.getName() + ".ping")
        .getBoundSql(null).getSql().trim());
    assertEquals("SELECT 2", configuration.getMappedStatement("other.vendor.ManualMapper.ping")
        .getBoundSql(null).getSql().trim());
    assertThrows(IllegalArgumentException.class, () -> configuration.getMappedStatement("ping"));
  }
}
