package com.stratmatrix.planning.source;

import static com.stratmatrix.planning.manual.Json.map;

import com.stratmatrix.planning.manual.BusinessException;
import com.stratmatrix.planning.manual.ManualRepository;
import com.stratmatrix.planning.manual.TopicUsageService;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/** Stable Java query facade used by Python. Host may reuse it with its own SourceFacts bean. */
@RestController
@RequestMapping("${planning.source.api-prefix:/api/plan/internal/source}")
@ConditionalOnProperty(name = "planning.source.enabled", havingValue = "true")
public class SourceFactsController {
  private final SourceFacts facts;
  private final TopicUsageService usage;
  private final String token;

  public SourceFactsController(
      SourceFacts facts,
      ManualRepository repository,
      @Value("${planning.source.token:}") String token) {
    this.facts = facts;
    this.usage = new TopicUsageService(repository);
    this.token = token;
    if (token.trim().isEmpty()) throw new IllegalStateException("Java资料查询令牌未配置");
  }

  @PostMapping("/{capability}/query")
  public Object query(
      @PathVariable String capability,
      @RequestHeader(value = "X-Integration-Token", defaultValue = "") String supplied,
      @RequestBody Map<String, Object> q) {
    if (!MessageDigest.isEqual(
        token.getBytes(StandardCharsets.UTF_8), supplied.getBytes(StandardCharsets.UTF_8)))
      throw new BusinessException(401, "Java资料查询认证失败");
    switch (capability) {
      case "accounts":
        return facts.accounts(q);
      case "topics":
        return facts.topics(q);
      case "marketing-contents":
        return facts.marketingContents(q);
      case "effective-marketing":
        return facts.effectiveMarketing(q);
      case "production-status":
        return facts.productionStatus(q);
      case "marketing-status":
        return facts.marketingStatus(q);
      case "topic-usage":
        return usage.query(q);
      default:
        throw new BusinessException(404, "未知资料查询能力");
    }
  }

  @ExceptionHandler(BusinessException.class)
  public ResponseEntity<Object> invalid(BusinessException error) {
    return ResponseEntity.status(error.status).body(map("detail", error.getMessage()));
  }
}
