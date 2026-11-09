package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.manual;

import com.pab.aitmp.aiis.godp.digital.marketing.services.mapper.xiangliang.ManualMapper;

import javax.sql.DataSource;
import org.apache.ibatis.session.SqlSessionFactory;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.core.io.ClassPathResource;

final class ManualTestMapper {
  private ManualTestMapper() {}

  static ManualMapper bind(DataSource dataSource) {
    try {
      SqlSessionFactoryBean bean = new SqlSessionFactoryBean();
      bean.setDataSource(dataSource);
      bean.setMapperLocations(new ClassPathResource("mapper/xiangliang/ManualMapper.xml"));
      SqlSessionFactory factory = bean.getObject();
      return new SqlSessionTemplate(factory).getMapper(ManualMapper.class);
    } catch (Exception e) {
      throw new IllegalStateException("Cannot bind manual MyBatis mapper", e);
    }
  }
}
