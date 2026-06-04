import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:intl/intl.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/constants/app_constants.dart';
import '../../domain/entities/memory.dart';

class MemoryListPage extends StatefulWidget {
  const MemoryListPage({super.key});

  @override
  State<MemoryListPage> createState() => _MemoryListPageState();
}

class _MemoryListPageState extends State<MemoryListPage> {
  MemoryCategory? _selectedCategory;
  final _searchController = TextEditingController();
  bool _isSearching = false;

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.primary,
      body: SafeArea(
        child: CustomScrollView(
          slivers: [
            _buildHeader(),
            _buildSearchBar(),
            _buildCategoryFilter(),
            _buildMemoryGrid(),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(24, 20, 24, 0),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '메모리',
                  style: Theme.of(context).textTheme.displayMedium,
                ),
                const SizedBox(height: 4),
                Text(
                  '내 음성 기억들',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ],
            ),
            IconButton(
              onPressed: () => setState(() => _isSearching = !_isSearching),
              icon: Icon(
                _isSearching ? Icons.close : Icons.search_rounded,
                color: AppColors.textSecondary,
              ),
            ),
          ],
        ).animate().fadeIn(),
      ),
    );
  }

  Widget _buildSearchBar() {
    return SliverToBoxAdapter(
      child: AnimatedContainer(
        duration: AppConstants.animMedium,
        height: _isSearching ? 72 : 0,
        child: _isSearching
            ? Padding(
                padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
                child: TextField(
                  controller: _searchController,
                  autofocus: true,
                  style: const TextStyle(color: AppColors.textPrimary),
                  decoration: const InputDecoration(
                    hintText: '메모리 검색...',
                    prefixIcon: Icon(Icons.search, color: AppColors.textTertiary),
                  ),
                ),
              )
            : const SizedBox.shrink(),
      ),
    );
  }

  Widget _buildCategoryFilter() {
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.only(top: 20),
        child: SizedBox(
          height: 40,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 24),
            children: [
              _FilterChip(
                label: '전체',
                isSelected: _selectedCategory == null,
                onTap: () => setState(() => _selectedCategory = null),
              ),
              ...MemoryCategory.values.map((c) => _FilterChip(
                label: '${c.emoji} ${c.label}',
                isSelected: _selectedCategory == c,
                onTap: () => setState(() => _selectedCategory = c),
              )),
            ],
          ),
        ).animate().fadeIn(delay: 100.ms),
      ),
    );
  }

  Widget _buildMemoryGrid() {
    // TODO: BLoC에서 데이터 가져오기
    // 임시 더미 데이터
    final dummies = List.generate(
      8,
      (i) => Memory(
        id: 'memory_$i',
        title: ['오늘 점심 메뉴 아이디어', '주간 업무 회의 메모', '내일 할 일 목록', '새 프로젝트 아이디어'][i % 4],
        rawTranscript: '원문 텍스트...',
        summary: ['샐러드와 파스타 조합이 어떨까. 이탈리안 레스토랑도 좋고...', '마케팅팀과의 Q3 목표 설정, 신규 캠페인 방향성 논의...', '보고서 작성, 팀 미팅 준비, 코드 리뷰 완료...', 'AI 기반 개인화 추천 시스템 아이디어, 사용자 행동 분석...'][i % 4],
        tags: [['점심', '음식'], ['회의', '업무'], ['할일'], ['아이디어', 'AI']][i % 4],
        createdAt: DateTime.now().subtract(Duration(hours: i * 6)),
        audioDuration: Duration(seconds: 30 + i * 15),
        category: MemoryCategory.values[i % MemoryCategory.values.length],
      ),
    );

    return SliverPadding(
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 100),
      sliver: SliverList(
        delegate: SliverChildBuilderDelegate(
          (context, i) => Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: _MemoryCard(
              memory: dummies[i],
              onTap: () => _openMemory(dummies[i]),
            ).animate(delay: (i * 50).ms).fadeInUp(duration: 300.ms),
          ),
          childCount: dummies.length,
        ),
      ),
    );
  }

  void _openMemory(Memory memory) {
    Navigator.pushNamed(context, '/memory/detail', arguments: memory);
  }
}

class _FilterChip extends StatelessWidget {
  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  const _FilterChip({
    required this.label,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: AppConstants.animFast,
        margin: const EdgeInsets.only(right: 8),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? AppColors.accent : AppColors.surfaceCard,
          borderRadius: BorderRadius.circular(AppConstants.borderRadiusCircle),
          border: Border.all(
            color: isSelected ? AppColors.accent : const Color(0xFF2A3F5F),
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: isSelected ? AppColors.primary : AppColors.textSecondary,
            fontSize: 13,
            fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
          ),
        ),
      ),
    );
  }
}

class _MemoryCard extends StatelessWidget {
  final Memory memory;
  final VoidCallback onTap;

  const _MemoryCard({required this.memory, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: AppColors.surfaceCard,
          borderRadius: BorderRadius.circular(AppConstants.borderRadiusLarge),
          border: Border.all(color: const Color(0xFF2A3F5F)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 카테고리 + 날짜
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppColors.secondaryGlow,
                    borderRadius: BorderRadius.circular(AppConstants.borderRadiusCircle),
                  ),
                  child: Text(
                    '${memory.category.emoji} ${memory.category.label}',
                    style: const TextStyle(
                      color: AppColors.secondary,
                      fontSize: 11,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
                Row(
                  children: [
                    const Icon(Icons.access_time, size: 12, color: AppColors.textTertiary),
                    const SizedBox(width: 4),
                    Text(
                      _formatDuration(memory.audioDuration),
                      style: const TextStyle(color: AppColors.textTertiary, fontSize: 12),
                    ),
                    const SizedBox(width: 12),
                    Text(
                      _formatDate(memory.createdAt),
                      style: const TextStyle(color: AppColors.textTertiary, fontSize: 12),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 12),
            // 요약
            Text(
              memory.summary,
              style: const TextStyle(
                color: AppColors.textPrimary,
                fontSize: 14,
                height: 1.5,
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            const SizedBox(height: 12),
            // 태그
            if (memory.tags.isNotEmpty)
              Wrap(
                spacing: 6,
                runSpacing: 4,
                children: memory.tags.take(3).map((tag) => Text(
                  '#$tag',
                  style: const TextStyle(
                    color: AppColors.accentDim,
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                  ),
                )).toList(),
              ),
          ],
        ),
      ),
    );
  }

  String _formatDuration(Duration d) {
    final mm = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final ss = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$mm:$ss';
  }

  String _formatDate(DateTime dt) {
    final now = DateTime.now();
    final diff = now.difference(dt);
    if (diff.inDays == 0) return '오늘';
    if (diff.inDays == 1) return '어제';
    return DateFormat('MM.dd').format(dt);
  }
}
