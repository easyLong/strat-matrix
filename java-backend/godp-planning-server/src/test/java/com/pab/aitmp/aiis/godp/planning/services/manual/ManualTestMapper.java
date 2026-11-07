package com.pab.aitmp.aiis.godp.planning.services.manual;

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
      bean.setMapperLocations(new ClassPathResource("mapper/ManualMapper.xml"));
      SqlSessionFactory factory = bean.getObject();
      return new SqlSessionTemplate(factory).getMapper(ManualMapper.class);
    } catch (Exception e) {
      throw new IllegalStateException("Cannot bind manual MyBatis mapper", e);
    }
  }
}
