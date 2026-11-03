package com.stratmatrix.planning.adapter.legacy;

import java.io.IOException;
import java.net.HttpURLConnection;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.ResponseErrorHandler;
import org.springframework.web.client.RestTemplate;

@Configuration
@Profile("local & !inside")
@EnableConfigurationProperties(LegacyPythonProperties.class)
public class LegacyPythonConfiguration {
    @Bean("legacyPythonHttp")
    public RestTemplate legacyPythonHttp(LegacyPythonProperties properties) {
        properties.baseUri();
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory() {
            @Override
            protected void prepareConnection(HttpURLConnection connection, String method) throws IOException {
                super.prepareConnection(connection, method);
                connection.setInstanceFollowRedirects(false);
            }
        };
        factory.setConnectTimeout(properties.getConnectTimeoutMs());
        factory.setReadTimeout(properties.getReadTimeoutMs());
        factory.setBufferRequestBody(false);
        RestTemplate client = new RestTemplate(factory);
        // Business 409/422/503 responses must reach the caller unchanged.
        client.setErrorHandler(new ResponseErrorHandler() {
            public boolean hasError(ClientHttpResponse response) { return false; }
            public void handleError(ClientHttpResponse response) { }
        });
        return client;
    }
}
