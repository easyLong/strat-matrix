package com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.vo.req;

import com.fasterxml.jackson.annotation.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.pab.aitmp.aiis.godp.digital.marketing.entity.xiangliang.support.Json;
import java.util.*;
import javax.validation.constraints.*;

/** Typed page/range envelope. Filter documents are versioned independently by each view. */
@JsonInclude(JsonInclude.Include.NON_NULL)
public final class PlanningQueryRequest {
  @NotNull @Min(1) public Integer page=1;
  @JsonAlias("page_size") @NotNull @Min(1) @Max(200) public Integer pageSize=20;
  @Pattern(regexp="account|batch|cycle|all|^$") public String mode;
  @JsonAlias("account_id") public String accountId;
  @JsonAlias("batch_id") public Long batchId;
  @JsonAlias("account_ids") public List<String> accountIds;
  @JsonAlias("batch_ids") public List<Long> batchIds;
  @JsonAlias("cycle_start") public String cycleStart;
  @JsonAlias("cycle_end") public String cycleEnd;
  public String unit, format;
  public JsonNode filters;
  @AssertTrue(message="筛选条件必须是对象") public boolean isFilterObject() { return filters==null || filters.isObject(); }
  public Map<String,Object> values() {
    Map<String,Object> out=Json.read(Json.write(this));
    out.remove("filterObject");
    for(String[] key:new String[][]{{"pageSize","page_size"},{"accountId","account_id"},{"batchId","batch_id"},
        {"accountIds","account_ids"},{"batchIds","batch_ids"},{"cycleStart","cycle_start"},{"cycleEnd","cycle_end"}})
      if(out.containsKey(key[0])) out.put(key[1],out.remove(key[0]));
    return out;
  }
}
