package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req;
import com.fasterxml.jackson.annotation.JsonAlias;
import javax.validation.constraints.*;

/** Catalog/lookup inputs for explicit POST queries; old read routes remain compatibility aliases. */
public final class CatalogQueryRequest {
  @Min(1) @Max(1000) public Integer limit;
  @NotNull @Min(0) public Integer offset=0;
  @JsonAlias("include_disabled") public boolean includeDisabled;
  @JsonAlias("publish_date") public String publishDate;
  @JsonAlias("plan_type") @Pattern(regexp="manual|auto") public String planType;
  @JsonAlias("topic_type") public String topicType;
  public int limitOr(int fallback) { return limit==null ? fallback:limit; }
}
