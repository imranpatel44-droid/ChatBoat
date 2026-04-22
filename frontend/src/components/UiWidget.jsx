import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion"; // for smooth animation

const STORAGE_PREFIX = 'chat_widget';
const SESSION_KEY_PREFIX = 'chat_widget_session';

// eslint-disable-next-line no-unused-vars
const NAME_EXTRACTION_SYSTEM_PROMPT = "You are an assistant that extracts a user's first name from short introductions. Return only the first name in Title Case with no additional words. If there is no clear name, return the word 'Friend'.";

const createMessage = (message = {}) => ({
  id: message.id || `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
  ...message,
});

const resolveScopeSuffix = (customerId, parentUrl) => {
  let hostIdentifier = '';

  if (parentUrl) {
    try {
      hostIdentifier = new URL(decodeURIComponent(parentUrl)).host;
    } catch (error) {
      console.warn('Failed to parse parentUrl for storage scope', error);
    }
  }

  if (!hostIdentifier && typeof document !== 'undefined' && document.referrer) {
    try {
      hostIdentifier = new URL(document.referrer).host;
    } catch (error) {
      hostIdentifier = document.referrer;
    }
  }

  if (!hostIdentifier && typeof window !== 'undefined') {
    hostIdentifier = window.location.host;
  }

  return `${customerId || 'guest'}_${hostIdentifier || 'global'}`;
};

const buildInitialMessages = (reason = null) => {
  const baseMessages = [
    { sender: "bot", text: "Hi there! Please select a service:" },
  ];

  if (reason === 'reset') {
    baseMessages.push({ sender: "bot", text: "Chat has been reset. Please select a service to continue." });
  } else if (reason === 'new') {
    baseMessages.push({ sender: "bot", text: "Starting a fresh conversation. Please select a service." });
  }

  return baseMessages.map((msg) => createMessage(msg));
};

const UiWidget = ({ apiKey, customerId, apiUrl = 'http://localhost:5000', parentUrl = '' }) => {
  const [isOpen, setIsOpen] = useState(true);
  const [messages, setMessages] = useState(buildInitialMessages());
  const [input, setInput] = useState("");
  const [userName, setUserName] = useState(null);
  const [selectedService, setSelectedService] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [storageKey, setStorageKey] = useState(null);
  const [isEnded, setIsEnded] = useState(false);
  const hasHydrated = useRef(false);
  const messagesEndRef = useRef(null);
  const streamingTimeouts = useRef([]);

  useEffect(() => {
    if (typeof document !== 'undefined') {
      const previousBodyBg = document.body.style.backgroundColor;
      const previousHtmlBg = document.documentElement.style.backgroundColor;
      document.body.style.backgroundColor = 'transparent';
      document.documentElement.style.backgroundColor = 'transparent';

      return () => {
        document.body.style.backgroundColor = previousBodyBg;
        document.documentElement.style.backgroundColor = previousHtmlBg;
      };
    }
  }, []);

  const fetchContextFromBackend = async (message) => {
    // Mirrors widget/chat headers so URL authorization still applies.
    let detectedParentUrl = '';

    if (parentUrl) {
      detectedParentUrl = decodeURIComponent(parentUrl);
    } else if (document.referrer) {
      detectedParentUrl = document.referrer;
    } else {
      detectedParentUrl = window.location.href;
    }

    const response = await fetch(`${apiUrl}/backend/api/widget/context`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Widget-API-Key': apiKey,
        'X-Customer-ID': customerId,
        'X-Parent-URL': detectedParentUrl,
      },
      body: JSON.stringify({ message }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || 'Failed to get context from server');
    }

    return response.json();
  };

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    hasHydrated.current = false;

    try {
      const scope = resolveScopeSuffix(customerId, parentUrl);
      const sessionStorageKey = `${SESSION_KEY_PREFIX}_${scope}`;
      let sessionId = localStorage.getItem(sessionStorageKey);

      if (!sessionId) {
        sessionId = `session_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
        localStorage.setItem(sessionStorageKey, sessionId);
      }

      const stateStorageKey = `${STORAGE_PREFIX}_${scope}_${sessionId}`;
      setStorageKey(stateStorageKey);

      const storedStateRaw = localStorage.getItem(stateStorageKey);
      if (storedStateRaw) {
        try {
          const storedState = JSON.parse(storedStateRaw);
          if (Array.isArray(storedState.messages) && storedState.messages.length) {
            setMessages(storedState.messages.map((msg) => createMessage(msg)));
          }
          if (typeof storedState.userName === 'string') {
            setUserName(storedState.userName);
          }
          if (typeof storedState.selectedService === 'string') {
            setSelectedService(storedState.selectedService);
          }
          if (typeof storedState.isOpen === 'boolean') {
            setIsOpen(storedState.isOpen);
          }
          if (typeof storedState.isEnded === 'boolean') {
            setIsEnded(storedState.isEnded);
          }
        } catch (parseError) {
          console.warn('Failed to parse stored widget state', parseError);
        }
      }
    } catch (error) {
      console.warn('Failed to restore widget state', error);
    } finally {
      hasHydrated.current = true;
    }
  }, [customerId, parentUrl]);

  useEffect(() => {
    if (!storageKey || !hasHydrated.current || typeof window === 'undefined') {
      return;
    }

    try {
      const stateToPersist = {
        messages,
        userName,
        selectedService,
        isOpen,
        isEnded,
        updatedAt: Date.now(),
      };
      localStorage.setItem(storageKey, JSON.stringify(stateToPersist));
    } catch (error) {
      console.warn('Failed to persist widget state', error);
    }
  }, [messages, userName, selectedService, isOpen, isEnded, storageKey]);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [messages]);

  useEffect(() => {
    return () => {
      streamingTimeouts.current.forEach(clearTimeout);
      streamingTimeouts.current = [];
    };
  }, []);

  const resetConversation = (reason = null) => {
    streamingTimeouts.current.forEach(clearTimeout);
    streamingTimeouts.current = [];
    setIsEnded(false);
    setIsLoading(false);
    setMessages(buildInitialMessages(reason));
    setUserName(null);
    setSelectedService(null);
    setInput("");

    if (storageKey) {
      try {
        localStorage.removeItem(storageKey);
      } catch (error) {
        console.warn('Failed to remove stored widget state', error);
      }
    }
  };

  const handleResetChat = () => {
    resetConversation('reset');
  };

  const streamBotResponse = (fullText) => {
    return new Promise((resolve) => {
      const sanitizedText = fullText || '';
      const messageId = `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

      setMessages((prev) => [...prev, createMessage({ id: messageId, sender: 'bot', text: '' })]);

      let index = 0;
      const chunkDelay = sanitizedText.length > 220 ? 12 : 18;

      const revealNextChunk = () => {
        index += 1;
        const nextText = sanitizedText.slice(0, index);
        setMessages((prev) => prev.map((msg) =>
          msg.id === messageId ? { ...msg, text: nextText } : msg
        ));

        if (index < sanitizedText.length) {
          const timeoutId = setTimeout(revealNextChunk, chunkDelay);
          streamingTimeouts.current.push(timeoutId);
        } else {
          resolve();
        }
      };

      revealNextChunk();
    });
  };

  const handleEndChat = () => {
    if (isEnded) {
      return;
    }

    setIsEnded(true);
    setIsLoading(false);
    setMessages((prev) => [
      ...prev,
      createMessage({ id: `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`, sender: "bot", text: "Chat has ended. Thank you for chatting with us!" })
    ]);
  };

  const handleNewChat = () => {
    resetConversation('new');
  };

  // eslint-disable-next-line no-unused-vars
  const sanitizeNameCandidate = (candidate) => {
    if (!candidate || typeof candidate !== 'string') {
      return '';
    }
    const words = candidate.match(/[A-Za-z][A-Za-z'-]*/g);
    if (!words || !words.length) {
      return '';
    }
    const first = words[0];
    return first.charAt(0).toUpperCase() + first.slice(1).toLowerCase();
  };

  const sendMessageToBackend = async (message, mode = 'chat') => {
    try {
      // Get the parent page's URL (where the widget is embedded)
      // Priority: 1) parentUrl prop (passed via query param), 2) document.referrer, 3) current URL
      let detectedParentUrl = '';
      
      if (parentUrl) {
        // Decode the URL that was passed as a query parameter
        detectedParentUrl = decodeURIComponent(parentUrl);
        console.log('Using parentUrl from query param:', detectedParentUrl);
      } else if (document.referrer) {
        detectedParentUrl = document.referrer;
        console.log('Using document.referrer:', document.referrer);
      } else {
        // Fallback to current URL (for testing)
        detectedParentUrl = window.location.href;
        console.log('Fallback to window.location.href:', window.location.href);
      }

      console.log('=== Widget Request Debug ===');
      console.log('Parent URL to send:', detectedParentUrl);
      console.log('API Key:', apiKey);
      console.log('Customer ID:', customerId);

      const response = await fetch(`${apiUrl}/backend/api/widget/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Widget-API-Key': apiKey,
          'X-Customer-ID': customerId,
          'X-Parent-URL': detectedParentUrl  // Send parent page URL
        },
        body: JSON.stringify({
          message: message,
          mode,
          service: selectedService || 'ChatGPT'
        })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to get response from server');
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error sending message:', error);
      if (error.message && error.message.toLowerCase().includes('unauthorized')) {
        return 'Unauthorized URL. This widget cannot respond on this site.';
      }
      return error.message || 'Sorry, there was an error connecting to the server. Please try again.';
    }
  };

  const handleSend = async () => {
    if (!input.trim() || isEnded) return;

    setMessages((prev) => [...prev, createMessage({ sender: "user", text: input })]);
    const userInput = input;
    setInput("");
    setIsLoading(true);

    try {
      if (!userName) {
        let cleanName = userInput;

        // Use backend API for name extraction - it will route to the appropriate service (ChatGPT/Gemini)
        const responseData = await sendMessageToBackend(userInput, 'name_capture');
        const extracted = responseData && typeof responseData === 'object' ? responseData.extractedName : null;
        cleanName = (extracted && typeof extracted === 'string') ? extracted : userInput;

        setUserName(cleanName);
        setMessages((prev) => [
          ...prev,
          createMessage({ sender: "bot", text: `Nice to meet you, ${cleanName}! 🌟` }),
          createMessage({ sender: "bot", text: `You selected: ${selectedService}` }),
          createMessage({ sender: "bot", text: "What can I do for you today?" }),
        ]);
        return;
      }

      const contextData = await fetchContextFromBackend(userInput);
      const prompt = contextData && typeof contextData === 'object' ? (contextData.prompt || userInput) : userInput;

      let botResponse = '';

      // Use backend API for chat responses - it will route to the appropriate service (ChatGPT/Gemini)
      const responseData = await sendMessageToBackend(prompt, 'chat');
      botResponse = responseData && typeof responseData === 'object' ? responseData.response : responseData;

      await streamBotResponse(botResponse);
    } catch (error) {
      console.error('Error in handleSend:', error);
      let errorMessage = 'Sorry, there was an error. Please try again.';
      if (error && error.message && error.message.toLowerCase().includes('unauthorized')) {
        errorMessage = 'Unauthorized URL. This widget cannot respond on this site.';
      } else if (error && error.message) {
        errorMessage = error.message;
      }

      setMessages((prev) => [
        ...prev,
        createMessage({ sender: "bot", text: errorMessage })
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleServiceSelect = (service) => {
    if (isEnded) {
      return;
    }

    setSelectedService(service === 'Default' || service === 'ChatGPT' ? 'ChatGPT' : service);
    setMessages((prev) => [
      ...prev,
      createMessage({ sender: "user", text: service }),
      createMessage({ sender: "bot", text: "Great! Now, what's your name?" }),
    ]);
  };

  return (
    <div>
      {/* Floating Button when closed */}
      {!isOpen && (
        <motion.button
          onClick={() => setIsOpen(true)}
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.95 }}
          style={{
            position: "fixed",
            bottom: "20px",
            right: "20px",
            borderRadius: "50%",
            width: "65px",
            height: "65px",
            background: "linear-gradient(135deg, #4e8cff 0%, #007bff 100%)",
            color: "white",
            border: "none",
            cursor: "pointer",
            fontSize: "26px",
          }}
        >
          💬
        </motion.button>
      )}

      {/* Chatbox when open */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 50 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 50 }}
            transition={{ duration: 0.3 }}
            style={{
              position: "fixed",
              bottom: "24px",
              right: "24px",
              width: "min(420px, calc(100vw - 32px))",
              height: "min(640px, calc(100vh - 32px))",
              backgroundColor: "rgba(255, 255, 255, 0.92)",
              borderRadius: "24px",
              display: "flex",
              flexDirection: "column",
              boxShadow: "0 24px 60px -20px rgba(15, 23, 42, 0.35)",
              overflow: "hidden",
              fontFamily: "system-ui, sans-serif",
              border: "1px solid rgba(79, 70, 229, 0.12)",
              backdropFilter: "blur(18px)",
              WebkitBackdropFilter: "blur(18px)",
            }}
          >
            {/* Header */}
            <div
              style={{
                padding: "22px 28px 18px",
                background: "linear-gradient(135deg, #4e8cff 0%, #007bff 100%)",
                color: "white",
                fontWeight: "bold",
                fontSize: "18px",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                boxShadow: "0 12px 24px -16px rgba(59, 130, 246, 0.6)",
                borderBottom: "1px solid rgba(255,255,255,0.18)",
              }}
            >
              <span>Chat Assistant 🤖</span>
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <button
                  onClick={handleResetChat}
                  disabled={isLoading}
                  style={{
                    background: "rgba(255,255,255,0.18)",
                    border: "none",
                    borderRadius: "999px",
                    padding: "6px 14px",
                    color: "white",
                    fontSize: "12px",
                    cursor: isLoading ? "not-allowed" : "pointer",
                    transition: "opacity 0.2s",
                    opacity: isLoading ? 0.6 : 1,
                    backdropFilter: "blur(4px)",
                  }}
                >
                  Reset
                </button>
                <button
                  onClick={handleEndChat}
                  disabled={isEnded}
                  style={{
                    background: isEnded ? "rgba(255,255,255,0.16)" : "rgba(255,255,255,0.28)",
                    border: "none",
                    borderRadius: "999px",
                    padding: "6px 14px",
                    color: "white",
                    fontSize: "12px",
                    cursor: isEnded ? "not-allowed" : "pointer",
                    transition: "opacity 0.2s",
                    opacity: isEnded ? 0.6 : 1,
                    backdropFilter: "blur(4px)",
                  }}
                >
                  End
                </button>
                <button
                  onClick={() => setIsOpen(false)}
                  style={{
                    background: "rgba(255,255,255,0.2)",
                    border: "none",
                    borderRadius: "50%",
                    width: "28px",
                    height: "28px",
                    color: "white",
                    fontSize: "16px",
                    cursor: "pointer",
                  }}
                >
                  ✖
                </button>
              </div>
            </div>

            {/* Messages */}
            <div
              style={{
                flex: 1,
                padding: "24px",
                overflowY: "auto",
                backgroundColor: "linear-gradient(180deg, rgba(249, 250, 255, 0.88) 0%, rgba(219, 234, 254, 0.94) 100%)",
                margin: "16px 24px",
                borderRadius: "20px",
                border: "1px solid rgba(59, 130, 246, 0.16)",
                boxShadow: "inset 0 1px 1px rgba(255,255,255,0.6)",
                display: "flex",
                flexDirection: "column",
                gap: "14px",
              }}
            >
              {messages.map((msg, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    justifyContent:
                      msg.sender === "user" ? "flex-end" : "flex-start",
                  }}
                >
                  <div
                    style={{
                      padding: "12px 18px",
                      borderRadius: "18px",
                      maxWidth: "82%",
                      fontSize: "15px",
                      lineHeight: "1.6",
                      whiteSpace: "pre-wrap",
                      background:
                        msg.sender === "user"
                          ? "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)"
                          : "#ffffff",
                      color: msg.sender === "user" ? "white" : "#1f2937",
                      border: msg.sender === "bot" ? "1px solid rgba(148, 163, 184, 0.35)" : "none",
                      borderBottomRightRadius: msg.sender === "user" ? "4px" : "18px",
                      borderBottomLeftRadius: msg.sender === "bot" ? "4px" : "18px",
                      boxShadow: msg.sender === "user"
                        ? "0 16px 24px -18px rgba(37, 99, 235, 0.55)"
                        : "0 12px 24px -20px rgba(71, 85, 105, 0.35)",
                    }}
                  >
                    {msg.text}
                  </div>
                </div>
              ))}

              <div ref={messagesEndRef} />

              {/* Show service buttons only if not selected */}
              {!selectedService && !isEnded && (
                <div style={{ display: "flex", gap: "10px", marginTop: "8px" }}>
                  {["Default", "ChatGPT", "Gemini"].map((service) => (
                    <button
                      key={service}
                      onClick={() => handleServiceSelect(service)}
                      style={{
                        flex: 1,
                        padding: "12px 16px",
                        borderRadius: "999px",
                        border: "1px solid rgba(59, 130, 246, 0.2)",
                        cursor: "pointer",
                        background: "rgba(255,255,255,0.92)",
                        fontSize: "13px",
                        fontWeight: "600",
                        color: "#3b4a6b",
                        transition: "all 0.2s",
                        boxShadow: "0 10px 20px -18px rgba(59, 130, 246, 0.55)",
                      }}
                      onMouseEnter={(e) => {
                        e.target.style.background = "linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%)";
                        e.target.style.color = "#1d4ed8";
                        e.target.style.borderColor = "rgba(37, 99, 235, 0.4)";
                      }}
                      onMouseLeave={(e) => {
                        e.target.style.background = "rgba(255,255,255,0.92)";
                        e.target.style.color = "#3b4a6b";
                        e.target.style.borderColor = "rgba(59, 130, 246, 0.2)";
                      }}
                    >
                      {service}
                    </button>
                  ))}
                </div>
              )}

              {isEnded && (
                <div style={{ display: "flex", justifyContent: "center", marginTop: "4px" }}>
                  <button
                    onClick={handleNewChat}
                    style={{
                      padding: "11px 28px",
                      borderRadius: "999px",
                      border: "none",
                      background: "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
                      color: "white",
                      fontSize: "14px",
                      fontWeight: "600",
                      cursor: "pointer",
                      transition: "transform 0.2s, box-shadow 0.2s",
                      boxShadow: "0 18px 28px -18px rgba(37, 99, 235, 0.65)",
                    }}
                    onMouseOver={(e) => {
                      e.target.style.transform = "translateY(-1px)";
                      e.target.style.boxShadow = "0 20px 32px -18px rgba(37, 99, 235, 0.75)";
                    }}
                    onMouseOut={(e) => {
                      e.target.style.transform = "translateY(0)";
                      e.target.style.boxShadow = "0 18px 28px -18px rgba(37, 99, 235, 0.65)";
                    }}
                  >
                    New Chat
                  </button>
                </div>
              )}

              {/* Loading indicator */}
              {isLoading && !isEnded && (
                <div style={{ display: "flex", justifyContent: "flex-start", marginTop: "8px" }}>
                  <div style={{
                    padding: "12px 16px",
                    borderRadius: "18px",
                    backgroundColor: "rgba(255,255,255,0.9)",
                    border: "1px solid rgba(148, 163, 184, 0.35)",
                  }}>
                    <div style={{ display: "flex", gap: "4px", color: "#475569", fontSize: "13px", alignItems: "center" }}>
                      <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#60a5fa", display: "inline-block", animation: "typing 1.4s infinite" }}></span>
                      <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#3b82f6", display: "inline-block", animation: "typing 1.4s infinite 0.2s" }}></span>
                      <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#1d4ed8", display: "inline-block", animation: "typing 1.4s infinite 0.4s" }}></span>
                    </div>
                  </div>
                </div>
              )}
            </div>


            {/* Input */}
            <div
              style={{
                padding: "20px 24px",
                borderTop: "1px solid rgba(148, 163, 184, 0.25)",
                display: "flex",
                gap: "12px",
                background: "rgba(239, 246, 255, 0.85)",
                backdropFilter: "blur(14px)",
              }}
            >
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                placeholder={isEnded ? "Chat ended." : "Type a message..."}
                disabled={isLoading || isEnded}
                style={{
                  flex: 1,
                  padding: "14px 20px",
                  borderRadius: "999px",
                  border: "1px solid rgba(148, 163, 184, 0.4)",
                  fontSize: "15px",
                  outline: "none",
                  background: "rgba(255,255,255,0.95)",
                  boxShadow: "inset 0 1px 1px rgba(255,255,255,0.6)",
                }}
              />
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handleSend}
                disabled={isLoading || isEnded}
                style={{
                  background: "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
                  color: "white",
                  border: "none",
                  borderRadius: "50%",
                  width: "48px",
                  height: "48px",
                  cursor: "pointer",
                  fontSize: "18px",
                  fontWeight: "bold",
                  boxShadow: "0 16px 30px -18px rgba(37, 99, 235, 0.6)",
                }}
              >
                ➤
              </motion.button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default UiWidget;
