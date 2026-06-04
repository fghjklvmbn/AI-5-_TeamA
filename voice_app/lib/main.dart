import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:get_it/get_it.dart';
import 'core/theme/app_theme.dart';
import 'core/network/stt_service.dart';
import 'core/network/llm_service.dart';
import 'core/network/tts_service.dart';
import 'features/record/presentation/bloc/record_bloc.dart';
import 'shared/widgets/main_shell.dart';

final getIt = GetIt.instance;

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // 상태바 스타일
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
      systemNavigationBarColor: AppColors.surface,
    ),
  );

  // 세로 고정
  await SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
  ]);

  // DI 초기화
  _setupDependencies();

  runApp(const VoiceMemoryApp());
}

void _setupDependencies() {
  // Services
  getIt.registerLazySingleton<SttService>(() => NativeSttService());
  getIt.registerLazySingleton<LlmService>(() => LlmService());
  getIt.registerLazySingleton<TtsService>(() => TtsService());
  getIt.registerLazySingleton<RecordingManager>(
    () => RecordingManager(sttService: getIt<SttService>()),
  );
}

class VoiceMemoryApp extends StatelessWidget {
  const VoiceMemoryApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiBlocProvider(
      providers: [
        BlocProvider(
          create: (_) => RecordBloc(
            recordingManager: getIt<RecordingManager>(),
            llmService: getIt<LlmService>(),
            ttsService: getIt<TtsService>(),
          ),
        ),
      ],
      child: MaterialApp(
        title: '음성 메모리',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.darkTheme,
        home: const MainShell(),
        onGenerateRoute: _generateRoute,
      ),
    );
  }

  Route<dynamic>? _generateRoute(RouteSettings settings) {
    switch (settings.name) {
      case '/settings':
        return MaterialPageRoute(
          builder: (_) => const Scaffold(
            body: Center(child: Text('설정 페이지')),
          ),
        );
      case '/memory/detail':
        return MaterialPageRoute(
          builder: (_) => const Scaffold(
            body: Center(child: Text('메모리 상세')),
          ),
        );
      default:
        return null;
    }
  }
}
