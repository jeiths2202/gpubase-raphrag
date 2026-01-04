# IMS Knowledge System - Quick Start Guide

## 🚀 5-Minute Setup

Get up and running with IMS Knowledge System in 5 minutes.

## Prerequisites

✅ Chrome browser installed
✅ Logged into your company's IMS system in Chrome
✅ Backend and Frontend servers running

## Step-by-Step Guide

### 1. Start the Servers

**Backend:**
```bash
# Terminal 1
cd gpubase-raphrag
python -m app.api.main --mode develop
```

**Frontend:**
```bash
# Terminal 2
cd gpubase-raphrag/frontend
npm run dev
```

### 2. Access the Knowledge App

Open browser: **http://localhost:3000/knowledge**

![Knowledge App](../frontend/src/assets/knowledge-app-screenshot.png)

### 3. Navigate to IMS Knowledge Service

Click on sidebar: **"IMS 지식 서비스"** (IMS Knowledge Service)

![IMS Tab](../frontend/src/assets/ims-tab-screenshot.png)

### 4. Connect to IMS System

1. Enter your IMS URL (default: `https://ims.tmaxsoft.com`)
2. Click **"SSO로 연결"** (Connect with SSO)
3. Wait 2-3 seconds for connection

![IMS Connection](../frontend/src/assets/ims-connection.png)

**What happens behind the scenes:**
- ✅ Extracts cookies from Chrome
- ✅ Creates authenticated session
- ✅ Validates connection with IMS

### 5. Ask Your First Question

Type a question in the chat interface:

```
프로젝트 X의 최신 진행 상황은?
```

Click **"전송"** (Send)

![IMS Chat](../frontend/src/assets/ims-chat.png)

### 6. View AI Response

The AI will:
1. ✅ Search IMS system for relevant data
2. ✅ Generate comprehensive answer
3. ✅ Automatically save as Knowledge Article

![IMS Response](../frontend/src/assets/ims-response.png)

### 7. Access Saved Knowledge

Your generated knowledge is automatically saved and can be accessed:
- **Knowledge Articles Tab:** View all IMS-generated articles
- **Search:** Find by keywords or tags
- **Share:** Share with team members

## Common Use Cases

### Use Case 1: Project Status Check

**Question:**
```
현재 진행 중인 프로젝트 목록과 각 프로젝트의 상태를 알려줘
```

**Result:**
- Real-time project data from IMS
- AI-formatted summary
- Saved as searchable knowledge

---

### Use Case 2: Resource Allocation

**Question:**
```
이번 달 리소스 할당 현황은?
```

**Result:**
- IMS resource data
- AI analysis and insights
- Historical comparison (if available)

---

### Use Case 3: Documentation Search

**Question:**
```
API 인증 방법에 대한 문서를 찾아줘
```

**Result:**
- IMS documentation search
- AI-extracted key points
- Direct links to source documents

## Troubleshooting

### ❌ Connection Failed

**Error:** "Cookie extraction failed"

**Solution:**
1. Make sure Chrome is running
2. Verify you're logged into IMS in Chrome
3. Try using "Default" profile (or check your Chrome profile name)

**Check Chrome Profile:**
```bash
# Windows
dir %LOCALAPPDATA%\Google\Chrome\User Data

# macOS
ls ~/Library/Application\ Support/Google/Chrome/

# Linux
ls ~/.config/google-chrome/
```

---

### ❌ Session Expired

**Error:** "SSO 세션이 만료되었습니다"

**Solution:**
1. Click **"연결 해제"** (Disconnect)
2. Click **"SSO로 연결"** (Reconnect)

---

### ❌ No Response from AI

**Error:** Silent failure or timeout

**Solution:**
1. Check backend logs: `tail -f logs/kms.log`
2. Verify RAG service is initialized
3. Check IMS system availability

## Advanced Features

### Custom IMS Endpoints

If your IMS system uses different URLs, you can customize:

```typescript
// frontend/src/features/knowledge/components/ContentTab.tsx
const [imsUrl, setImsUrl] = useState('https://your-custom-ims.com');
```

### Multi-Profile Support

Switch between Chrome profiles:

```json
{
  "chrome_profile": "Profile 1"  // or "Work", "Personal", etc.
}
```

### Language Selection

The system auto-detects language, but you can specify:

```json
{
  "query": "What is the project status?",
  "language": "en"  // ko, ja, or en
}
```

## Performance Tips

### 🚀 Faster Responses

1. **Specific Questions:** More specific = faster IMS search
   - ❌ "Tell me about projects"
   - ✅ "Show me Project X status for December 2025"

2. **Stay Connected:** Keep session active
   - Don't disconnect/reconnect frequently
   - Session cookies are cached

3. **Use Tags:** Tag generated knowledge for easy retrieval
   - Auto-tagged with: `["IMS", "AI생성", "SSO"]`
   - Add custom tags in Knowledge Articles tab

## Next Steps

### 🎯 Learn More

- **Full Documentation:** [IMS_KNOWLEDGE_SYSTEM.md](./IMS_KNOWLEDGE_SYSTEM.md)
- **API Reference:** [API_REFERENCE.md](./API_REFERENCE.md)
- **Architecture Guide:** [ARCHITECTURE.md](./ARCHITECTURE.md)

### 🛠️ Customization

- **Add Custom Endpoints:** Modify `ims_sso.py`
- **Customize UI:** Edit `ContentTab.tsx`
- **Extend Knowledge Schema:** Update `knowledge_article.py`

### 🤝 Contribute

Found a bug or have a feature request?
- **GitHub Issues:** https://github.com/your-repo/issues
- **Pull Requests:** Welcome!

## FAQs

**Q: Do I need to close Chrome?**
A: No! The system works while Chrome is running.

**Q: Is my data secure?**
A: Yes. Cookies are extracted locally, encrypted, and session-only.

**Q: Can I use multiple IMS systems?**
A: Currently one at a time. Multi-IMS support is planned.

**Q: How long do sessions last?**
A: Until you disconnect or cookies expire (typically 1-24 hours).

**Q: Can I share generated knowledge?**
A: Yes! Knowledge articles are saved and shareable through the Knowledge Base.

**Q: What if IMS is down?**
A: RAG service continues to work with existing knowledge base.

---

## 🎉 Success!

You're now ready to leverage IMS data with AI-powered knowledge generation!

**Happy Knowledge Building! 🚀**
