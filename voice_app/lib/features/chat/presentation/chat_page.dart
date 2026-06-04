import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/constants/app_constants.dart';
import '../../domain/entities/chat_message.dart';

class ChatPage extends StatefulWidget {
  const ChatPage({super.key});

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final _textController = TextEditingController();
  final _scrollController = ScrollController();
  bool _isVoiceMode = true;
  bool _isRecordingForChat = false;

  // 임시 더미 메시지
  final List<ChatMessage> _messages = [
    ChatMessage(
      id: '0',
      content: '안녕하세요! 저는 당신의 음성 메모들을 기억하고 있어요. 무엇이든 물어보세요.',
      role: ChatRole.assistant,
      createdAt: DateTime.now().subtract(const Duration(minutes: 5)),
    ),
  ];

  @override
  void dispose() {
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.primary,
      body: SafeArea(
        child: Column(
          children: [
            _buildHeader(),
            Expanded(child: _buildMessageList()),
            _buildInputArea(),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 0),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              gradient: AppColors.accentGradient,
            ),
            child: const Icon(Icons.auto_awesome, color: Colors.white, size: 20),
          ),
          const SizedBox(width: 12),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'AI 어시스턴트',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const Text(
                '메모리를 기억하고 있어요',
                style: TextStyle(
                  color: AppColors.success,
                  fontSize: 12,
                ),
              ),
            ],
          ),
          const Spacer(),
          // 모드 전환 (음성 / 텍스트)
          GestureDetector(
            onTap: () => setState(() => _isVoiceMode = !_isVoiceMode),
            child: AnimatedContainer(
              duration: AppConstants.animFast,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: AppColors.surfaceCard,
                borderRadius: BorderRadius.circular(AppConstants.borderRadiusCircle),
                border: Border.all(color: const Color(0xFF2A3F5F)),
              ),
              child: Row(
                children: [
                  Icon(
                    _isVoiceMode ? Icons.mic : Icons.keyboard,
                    size: 16,
                    color: AppColors.accent,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    _isVoiceMode ? '음성' : '텍스트',
                    style: const TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ).animate().fadeIn(),
    );
  }

  Widget _buildMessageList() {
    return ListView.builder(
      controller: _scrollController,
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
      itemCount: _messages.length,
      itemBuilder: (context, i) {
        return _MessageBubble(
          message: _messages[i],
          prevMessage: i > 0 ? _messages[i - 1] : null,
        ).animate(delay: (i * 30).ms).fadeInUp(duration: 250.ms);
      },
    );
  }

  Widget _buildInputArea() {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border(
          top: BorderSide(color: const Color(0xFF2A3F5F), width: 1),
        ),
      ),
      child: _isVoiceMode ? _buildVoiceInput() : _buildTextInput(),
    );
  }

  Widget _buildVoiceInput() {
    return Row(
      children: [
        Expanded(
          child: GestureDetector(
            onTapDown: (_) {
              setState(() => _isRecordingForChat = true);
              // TODO: 녹음 시작
            },
            onTapUp: (_) {
              setState(() => _isRecordingForChat = false);
              // TODO: 녹음 중지 + STT + LLM
            },
            onTapCancel: () {
              setState(() => _isRecordingForChat = false);
            },
            child: AnimatedContainer(
              duration: AppConstants.animFast,
              height: 56,
              decoration: BoxDecoration(
                color: _isRecordingForChat ? AppColors.accentGlow : AppColors.surfaceCard,
                borderRadius: BorderRadius.circular(AppConstants.borderRadiusLarge),
                border: Border.all(
                  color: _isRecordingForChat
                      ? AppColors.accent
                      : const Color(0xFF2A3F5F),
                ),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    Icons.mic,
                    color: _isRecordingForChat ? AppColors.accent : AppColors.textTertiary,
                    size: 20,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    _isRecordingForChat ? '말하는 중...' : '눌러서 말하기',
                    style: TextStyle(
                      color: _isRecordingForChat
                          ? AppColors.accent
                          : AppColors.textTertiary,
                      fontSize: 14,
                      fontWeight: _isRecordingForChat
                          ? FontWeight.w600
                          : FontWeight.w400,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildTextInput() {
    return Row(
      children: [
        Expanded(
          child: TextField(
            controller: _textController,
            style: const TextStyle(color: AppColors.textPrimary, fontSize: 14),
            decoration: const InputDecoration(
              hintText: '메시지 입력...',
            ),
            maxLines: null,
            onSubmitted: _sendTextMessage,
          ),
        ),
        const SizedBox(width: 8),
        GestureDetector(
          onTap: () => _sendTextMessage(_textController.text),
          child: Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: const LinearGradient(
                colors: [AppColors.accent, AppColors.secondary],
              ),
            ),
            child: const Icon(Icons.send_rounded, color: Colors.white, size: 20),
          ),
        ),
      ],
    );
  }

  void _sendTextMessage(String text) {
    if (text.trim().isEmpty) return;

    final userMsg = ChatMessage(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      content: text.trim(),
      role: ChatRole.user,
      createdAt: DateTime.now(),
    );

    setState(() {
      _messages.add(userMsg);
      _textController.clear();
    });

    _scrollToBottom();
    // TODO: LLM 응답 처리
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: AppConstants.animMedium,
          curve: Curves.easeOut,
        );
      }
    });
  }
}

class _MessageBubble extends StatelessWidget {
  final ChatMessage message;
  final ChatMessage? prevMessage;

  const _MessageBubble({required this.message, this.prevMessage});

  @override
  Widget build(BuildContext context) {
    final isUser = message.isUser;
    final showAvatar = !isUser &&
        (prevMessage == null || prevMessage!.isUser);

    return Padding(
      padding: EdgeInsets.only(
        bottom: 8,
        left: isUser ? 48 : 0,
        right: isUser ? 0 : 48,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        mainAxisAlignment:
            isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        children: [
          if (!isUser && showAvatar) ...[
            Container(
              width: 32,
              height: 32,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                gradient: AppColors.accentGradient,
              ),
              child: const Icon(Icons.auto_awesome, color: Colors.white, size: 16),
            ),
            const SizedBox(width: 8),
          ] else if (!isUser) ...[
            const SizedBox(width: 40),
          ],
          Flexible(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                color: isUser ? AppColors.accent : AppColors.surfaceCard,
                borderRadius: BorderRadius.only(
                  topLeft: const Radius.circular(16),
                  topRight: const Radius.circular(16),
                  bottomLeft: Radius.circular(isUser ? 16 : 4),
                  bottomRight: Radius.circular(isUser ? 4 : 16),
                ),
                border: isUser
                    ? null
                    : Border.all(color: const Color(0xFF2A3F5F)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (message.isStreaming)
                    _buildStreamingIndicator()
                  else
                    Text(
                      message.content,
                      style: TextStyle(
                        color: isUser ? AppColors.primary : AppColors.textPrimary,
                        fontSize: 14,
                        height: 1.5,
                      ),
                    ),
                  // 오디오 재생 버튼 (TTS)
                  if (!isUser && message.audioPath != null)
                    _buildAudioPlayer(message.audioPath!),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStreamingIndicator() {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(3, (i) =>
        Container(
          width: 6, height: 6,
          margin: const EdgeInsets.symmetric(horizontal: 2),
          decoration: const BoxDecoration(
            color: AppColors.accent,
            shape: BoxShape.circle,
          ),
        ).animate(delay: (i * 150).ms, onPlay: (c) => c.repeat())
          .fadeOut(duration: 400.ms)
          .then()
          .fadeIn(duration: 400.ms),
      ),
    );
  }

  Widget _buildAudioPlayer(String audioPath) {
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: GestureDetector(
        onTap: () {
          // TODO: TTS 오디오 재생
        },
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: const [
            Icon(Icons.volume_up_rounded, color: AppColors.accent, size: 16),
            SizedBox(width: 4),
            Text(
              '음성 재생',
              style: TextStyle(
                color: AppColors.accent,
                fontSize: 12,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
