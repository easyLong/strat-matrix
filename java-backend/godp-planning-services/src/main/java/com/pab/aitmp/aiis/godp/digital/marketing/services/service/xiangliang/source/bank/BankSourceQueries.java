package com.pab.aitmp.aiis.godp.digital.marketing.services.service.xiangliang.source.bank;

import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.error.BusinessException;
import java.util.*;

/**
 * Implement via existing bank services, or use MapperBankSourceQueries for SQL. No default data.
 */
public interface BankSourceQueries {
  default void verifyReady() {
    for (java.lang.reflect.Method method : BankSourceQueries.class.getMethods()) {
      if (method.getName().equals("verifyReady") || java.lang.reflect.Modifier.isStatic(method.getModifiers())) continue;
      try {
        if (getClass().getMethod(method.getName(), method.getParameterTypes()).getDeclaringClass()==BankSourceQueries.class)
          throw new IllegalStateException("行内资料方法尚未实现："+method.getName());
      } catch (NoSuchMethodException impossible) { throw new IllegalStateException("行内资料方法缺失"); }
    }
  }
  default BankSourceContracts.PageRows accounts(BankSourceContracts.Accounts query) {
    throw missing("账号查询");
  }

  default BankSourceContracts.PageRows topics(BankSourceContracts.Topics query) {
    throw missing("选题查询");
  }

  default BankSourceContracts.PageRows marketingContents(BankSourceContracts.Marketing query) {
    throw missing("营销内容查询");
  }

  default List<Map<String, Object>> effectiveMarketing(BankSourceContracts.Placement query) {
    throw missing("有效营销投放查询");
  }

  default List<Map<String, Object>> productionStatus(BankSourceContracts.Production query) {
    throw missing("内容生产状态查询");
  }

  default List<Map<String, Object>> marketingStatus(BankSourceContracts.MarketingStatus query) {
    throw missing("营销需求进度查询");
  }

  default List<Map<String, Object>> approvedDemandContents(
      BankSourceContracts.ApprovedDemand query) {
    throw missing("营销过审分配查询");
  }

  static BusinessException missing(String capability) {
    return new BusinessException(503, "行内资料查询尚未接入：" + capability);
  }
}
