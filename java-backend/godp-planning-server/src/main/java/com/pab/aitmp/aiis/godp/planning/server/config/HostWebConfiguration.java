package com.pab.aitmp.aiis.godp.planning.server.config;

import com.pab.aitmp.aiis.godp.planning.api.context.RequestContexts;
import com.pab.aitmp.aiis.godp.planning.api.host.HostAccess;
import com.pab.aitmp.aiis.godp.planning.api.host.HostContextProvider;
import com.pab.aitmp.aiis.godp.planning.entity.context.PlanningRequestContext;

import com.pab.aitmp.aiis.godp.planning.api.port.ManualPorts;
import javax.servlet.http.*;
import com.pab.aitmp.aiis.godp.planning.api.host.PlanningPermission;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.*;
import org.springframework.web.servlet.AsyncHandlerInterceptor;
import org.springframework.web.servlet.config.annotation.*;

/** Host page access policy; machine-source calls retain their separate controller token check. */
@Configuration
@Profile("inside")
@ConditionalOnProperty(name = "planning.host.enabled", havingValue = "true")
public class HostWebConfiguration implements WebMvcConfigurer {
  private final HostAccess access;
  private final HostContextProvider contexts;
  private static final String SCOPE = HostWebConfiguration.class.getName() + ".scope";
  private final String prefix, source;

  public HostWebConfiguration(
      HostAccess access,
      ManualPorts.Actor actor,
      ObjectProvider<HostContextProvider> contexts,
      @Value("${planning.api-prefix:/api/plan}") String prefix,
      @Value("${planning.source.api-prefix:/api/plan/internal/source}") String source) {
    this.access = access;
    this.contexts =
        contexts.getIfAvailable(() -> request -> PlanningRequestContext.identity(actor.current()));
    this.prefix = prefix;
    this.source = source;
  }

  @Override
  public void addInterceptors(InterceptorRegistry registry) {
    registry
        .addInterceptor(
            new AsyncHandlerInterceptor() {
              @Override
              public boolean preHandle(
                  HttpServletRequest request, HttpServletResponse response, Object handler) {
                if(handler instanceof org.springframework.web.method.HandlerMethod) {
                  org.springframework.web.method.HandlerMethod method=(org.springframework.web.method.HandlerMethod)handler;
                  PlanningPermission required=method.getMethodAnnotation(PlanningPermission.class);
                  if(required==null) required=org.springframework.core.annotation.AnnotatedElementUtils.findMergedAnnotation(method.getBeanType(),PlanningPermission.class);
                  if(required!=null) request.setAttribute(PlanningPermission.REQUEST_ATTRIBUTE,required.value().clone());
                }
                access.authorize(request);
                PlanningRequestContext context =
                    java.util.Objects.requireNonNull(contexts.resolve(request), "宿主请求上下文未返回");
                RequestContexts.Scope scope = RequestContexts.open(context);
                try {
                  request.setAttribute(SCOPE, scope);
                  response.setHeader(RequestContexts.TRACE_HEADER, context.traceId);
                } catch (RuntimeException failure) {
                  scope.close();
                  throw failure;
                }
                return true;
              }

              @Override
              public void afterCompletion(
                  HttpServletRequest request,
                  HttpServletResponse response,
                  Object handler,
                  Exception error) {
                close(request);
              }

              @Override
              public void afterConcurrentHandlingStarted(
                  HttpServletRequest request, HttpServletResponse response, Object handler) {
                close(request);
              }

              private void close(HttpServletRequest request) {
                Object scope = request.getAttribute(SCOPE);
                request.removeAttribute(SCOPE);
                if (scope instanceof RequestContexts.Scope) ((RequestContexts.Scope) scope).close();
              }
            })
        .addPathPatterns(prefix + "/**")
        .excludePathPatterns(source + "/**");
  }
}
