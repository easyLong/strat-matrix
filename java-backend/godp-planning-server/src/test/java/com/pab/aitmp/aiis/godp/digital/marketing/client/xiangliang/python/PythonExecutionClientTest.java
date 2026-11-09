package com.pab.aitmp.aiis.godp.digital.marketing.client.xiangliang.python;

import java.net.URI;
import java.util.Arrays;
import java.util.Collections;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;

class PythonExecutionClientTest {
    @Test
    void sendsServerTokenAndAcceptsCoalescedHints() {
        RestTemplate http = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.createServer(http);
        server.expect(requestTo("http://python.test/api/internal/wakeup"))
                .andExpect(method(HttpMethod.POST)).andExpect(header("X-Integration-Token", "test-token"))
                .andExpect(content().json("{\"jobs\":[\"manual\",\"planning\"]}"))
                .andRespond(withStatus(HttpStatus.ACCEPTED).contentType(MediaType.APPLICATION_JSON)
                        .body("{\"status\":\"accepted\",\"accepted_jobs\":[\"manual\"],\"coalesced_jobs\":[\"planning\"]}"));
        new PythonExecutionClient(URI.create("http://python.test"), "test-token", http)
                .wakeup(Arrays.asList("manual", "planning"));
        server.verify();
    }

    @Test
    void neverMistakesGenericSuccessOrIncompleteReceiptForAcceptance() {
        for (String body : Arrays.asList("{}", "{\"status\":\"accepted\",\"accepted_jobs\":[],\"coalesced_jobs\":[]}")) {
            RestTemplate http = new RestTemplate();
            MockRestServiceServer server = MockRestServiceServer.createServer(http);
            server.expect(requestTo("http://python.test/api/internal/wakeup"))
                    .andRespond(withStatus(HttpStatus.ACCEPTED).contentType(MediaType.APPLICATION_JSON).body(body));
            PythonExecutionClient client = new PythonExecutionClient(URI.create("http://python.test"), "test-token", http);
            assertThrows(IllegalStateException.class, () -> client.wakeup(Collections.singletonList("manual")));
        }
    }
}
