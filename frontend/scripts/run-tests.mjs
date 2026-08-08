/**
 * 프론트엔드 화이트박스 테스트 실행 스크립트
 */

import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = process.cwd();
const TESTS_FOLDER = path.join(PROJECT_ROOT, 'src');

// 테스트 결과 저장 파일
const RESULTS_FILE = path.join(PROJECT_ROOT, 'test-results.json');

/**
 * 테스트 커버리지 분석
 */
async function analyzeCoverage() {
  console.log('\n📊 [테스트 커버리지 분석]\n');

  const testFiles = await fs.promises.readdir(TESTS_FOLDER).then(f =>
    f.endsWith('.test.tsx') || f.endsWith('.test.ts') ? f : null
  );

  const results = {
    timestamp: new Date().toISOString(),
    totalTestFiles: 0,
    passedTests: 0,
    failedTests: 0,
    coverage: {},
  };

  // 각 테스트 파일 처리
  const testExtensions = ['.tsx', '.ts'];
  
  for (const dir of ['components', 'utils']) {
    if (!fs.existsSync(path.join(TESTS_FOLDER, dir))) continue;
    
    const filesInDir = await fs.promises.readdir(
      path.join(TESTS_FOLDER, dir)
    );

    for (const file of filesInDir) {
      const ext = testExtensions.find(e => file.endsWith(e));
      if (!ext) continue;

      const filePath = path.join(TESTS_FOLDER, dir, file);
      const content = await fs.promises.readFile(filePath, 'utf-8');
      
      // 간단한 코드 분석 (실제 커버리지는 istanbul/nyc 사용)
      const describeBlocks = (content.match(/describe\(/g) || []).length;
      const itBlocks = (content.match(/it\(/g) || []).length;
      
      results.coverage[dir + file] = {
        describeCount: describeBlocks,
        itCount: itBlocks,
        estimatedCoverage: `${(describeBlocks > 0 ? 30 : 0)}%`
      };

      results.totalTestFiles++;
    }
  }

  // JSON 파일로 저장
  await fs.promises.writeFile(RESULTS_FILE, JSON.stringify(results, null, 2));

  console.log('총 테스트 파일:', results.totalTestFiles);
  console.log('테스트 결과 파일:', RESULTS_FILE);
}

/**
 * Jest 테스트 실행
 */
async function runJestTests() {
  console.log('\n🧪 [Jest Unit Test 실행]\n');

  try {
    const jestCommand = 'npx jest --config jest.config.cjs';
    console.log(`명령어: ${jestCommand}`);
    
    // Jest 테스트 실행 (CI 환경용)
    execSync(jestCommand, {
      stdio: 'inherit',
      cwd: PROJECT_ROOT,
      timeout: 120_000, // 2 분 제한
    });

    console.log('\n✅ [단위 테스트 통과]\n');
  } catch (error) {
    console.error('\n❌ [단위 테스트 실패:', error.message + ']\n');
    process.exitCode = 1;
  }
}

/**
 * React Native E2E 테스트 준비
 */
async function prepareE2ETests() {
  console.log('\n📱 [E2E 테스트 준비]\n');

  const e2eFolder = path.join(PROJECT_ROOT, 'e2e');
  
  if (!fs.existsSync(e2eFolder)) {
    console.log('⚠️  E2E 테스트 폴더가 없습니다. 생성 중...');
    // Detox 설정 파일 생성
    const detoxConfig = `# detox.config.js
module.exports = {
  testRunner: 'jest',
  settings: {
    jest: {
      globalSetup: './setup-jest.js',
    },
  },
  testRunnerCommand: 'npx jest --config ./jest.e2e.config.cjs',
};

/**
 * Detox E2E 테스트 설정
 * 
 * @see https://wix.github.io/Detox/docs/
 */`;

    await fs.promises.writeFile(
      path.join(PROJECT_ROOT, 'detox.config.js'),
      detoxConfig
    );

    console.log('✅ detox.config.js 생성됨');
  } else {
    console.log('✅ detox.config.js 이미 존재함');
  }
}

/**
 * 테스트 요약 리포트 출력
 */
function printSummary() {
  console.log('\n' + '='.repeat(60));
  console.log('📋 [테스트 실행 요약]');
  console.log('='.repeat(60));
  
  const testFiles = ['components', 'utils', 'AuthContext', 'api'];
  const summary = {
    timestamp: new Date().toISOString(),
    status: 'completed',
    testFiles,
    recommendations: [
      '단위 테스트 커버리지를 60% 이상 확보하세요.',
      'Integration Test 를 추가하여 컴포넌트 간 상호작용 검증',
      'E2E 테스트를 Detox/Appium 으로 구현하여 전체 플로우 검증',
      'CI/CD 파이프라인에 테스트 통합 (GitHub Actions 등)',
    ],
  };

  console.log('테스트 파일:', testFiles.join(', '));
  console.log('\n추천 사항:');
  summary.recommendations.forEach((rec, idx) => {
    console.log(`  ${idx + 1}. ${rec}`);
  });

  console.log('='.repeat(60) + '\n');
}

// 메인 실행 흐름
async function main() {
  console.log('MemoryPal Frontend White-Box Test Runner');
  console.log('='.repeat(60));
  
  // 단계별 테스트 실행
  await runJestTests();
  
  if (process.exitCode === 0) {
    printSummary();
  }

  process.exit(process.exitCode || 0);
}

main().catch(error => {
  console.error('Fatal error:', error.message);
  process.exit(1);
});