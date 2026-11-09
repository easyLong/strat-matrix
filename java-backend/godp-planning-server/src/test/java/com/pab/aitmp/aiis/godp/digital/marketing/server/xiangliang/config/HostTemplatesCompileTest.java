package com.pab.aitmp.aiis.godp.digital.marketing.server.xiangliang.config;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Collectors;
import javax.tools.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.*;

/** Compile the actual handoff templates against current public contracts, without activating them. */
class HostTemplatesCompileTest {
  @TempDir Path temporary;

  @Test
  void everyHostTemplateCompilesWithJava8AndTheExportedContracts() throws Exception {
    JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
    assertNotNull(compiler, "模板编译验收需要JDK，不能仅使用JRE");
    List<Path> templates;
    try (java.util.stream.Stream<Path> paths = Files.list(Paths.get("host-integration"))) {
      templates = paths.filter(p -> p.getFileName().toString().endsWith(".java.example"))
          .sorted().collect(Collectors.toList());
    }
    assertFalse(templates.isEmpty(), "宿主接入模板缺失");
    List<File> sources = new ArrayList<>();
    for (Path template : templates) {
      Path source = temporary.resolve(template.getFileName().toString().replace(".example", ""));
      Files.copy(template, source);
      sources.add(source.toFile());
    }
    Path classes = Files.createDirectory(temporary.resolve("classes"));
    DiagnosticCollector<JavaFileObject> errors = new DiagnosticCollector<>();
    try (StandardJavaFileManager files = compiler.getStandardFileManager(errors, Locale.ROOT, StandardCharsets.UTF_8)) {
      List<String> options = Arrays.asList("-proc:none", "-encoding", "UTF-8", "-source", "1.8", "-target", "1.8",
          "-classpath", System.getProperty("surefire.test.class.path", System.getProperty("java.class.path")),
          "-d", classes.toString());
      boolean success = compiler.getTask(null, files, errors, options, null, files.getJavaFileObjectsFromFiles(sources)).call();
      assertTrue(success, () -> errors.getDiagnostics().stream().map(Object::toString).collect(Collectors.joining("\n")));
    }
  }
}
