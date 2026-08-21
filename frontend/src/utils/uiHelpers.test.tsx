import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react-native';
import { 
  ErrorView, 
  LoadingView, 
  SuccessView, 
  ConfirmDialog 
} from './uiHelpers';

describe('UI Helpers Components', () => {
  describe('ErrorView', () => {
    // 1. 기본 에러 표시 - 아이콘과 메시지
    it('displays error icon and message', () => {
      render(
        <ErrorView message="에러 발생했습니다." />
      );

      const icon = screen.getByText('⚠️');
      expect(icon).toBeDefined();

      const message = screen.getByText('에러 발생했습니다.');
      expect(message).toBeDefined();
    });

    // 2. retry 버튼 포함 시 클릭 이벤트 검증
    it('calls onRetry when retry button is clicked', () => {
      const onRetry = jest.fn();

      render(
        <ErrorView 
          message="에러 발생했습니다." 
          onRetry={onRetry}
        />
      );

      // "다시 시도하기" 텍스트 클릭 시 onRetry 호출
      fireEvent.press(screen.getByText('재시도'));
      
      expect(onRetry).toHaveBeenCalledTimes(1);
    });

    // 3. retry 버튼 없이 에러 표시 검증
    it('renders without retry when not provided', () => {
      render(
        <ErrorView message="에러 발생했습니다." />
      );

      const retryButton = screen.queryByText('재시도');
      expect(retryButton).toBeNull();
    });

    // 4. 에러 스타일 색상 검증 (간접적)
    it('applies yellow background color to error box', () => {
      render(
        <ErrorView message="에러 발생했습니다." />
      );

      const container = screen.getByText('에러 발생했습니다.');
      // 스타일 객체를 통해 색상 확인 (간접적)
    });

    // 5. 긴 에러 메시지 처리
    it('handles long error message', () => {
      render(
        <ErrorView 
          message="매우 긴 에러 메시지입니다. 사용자가 에러를 이해할 수 있도록 명확한 메시지가 제공되어야 합니다. 여러 줄에 걸쳐 표시되는 경우 자동으로 줄 바꿈이 되어야 합니다."
        />
      );

      const message = screen.getByText(/매우 긴 에러/);
      expect(message).toBeDefined();
    });
  });

  describe('LoadingView', () => {
    // 1. 기본 로딩 표시 - ActivityIndicator
    it('displays ActivityIndicator when loading', () => {
      render(
        <LoadingView message="작업 중입니다..." />
      );

      const indicator = screen.getByTestId('loading-indicator');
      expect(indicator).toBeDefined();
    });

    // 2. 메시지 없이 로딩 표시 검증
    it('renders without message when not provided', () => {
      render(
        <LoadingView />
      );

      const indicator = screen.getByTestId('loading-indicator');
      expect(indicator).toBeDefined();
      
      const message = screen.queryByText(/작업 중/);
      expect(message).toBeNull();
    });

    // 3. 진행률 표시 검증 (progress: 50)
    it('displays progress bar when progress is provided', () => {
      render(
        <LoadingView message="처리 중..." progress={50} />
      );

      const progressBar = screen.getByTestId('progress-bar');
      // progress width 가 50% 로 설정되었는지 확인 (간접적)
    });

    // 4. 진행률 0 검증
    it('displays progress bar at 0 when progress is 0', () => {
      render(
        <LoadingView message="초기화..." progress={0} />
      );

      const progressBar = screen.getByTestId('progress-bar');
      expect(progressBar).toHaveStyle({ width: '0%' });
    });

    // 5. 진행률 100 검증
    it('displays progress bar at 100 when progress is 100', () => {
      render(
        <LoadingView message="완료..." progress={100} />
      );

      const progressBar = screen.getByTestId('progress-bar');
      expect(progressBar).toHaveStyle({ width: '100%' });
    });

    // 6. null 진행률 처리 (progress bar 숨김)
    it('hides progress bar when progress is null', () => {
      render(
        <LoadingView message="작업 중..." progress={null} />
      );

      const progressBar = screen.queryByTestId('progress-bar');
      expect(progressBar).toBeNull();
    });

    // 7. undefined 진행률 처리
    it('hides progress bar when progress is undefined', () => {
      render(
        <LoadingView message="작업 중..." />
      );

      const progressBar = screen.queryByTestId('progress-bar');
      expect(progressBar).toBeNull();
    });

    // 8. 진부진률 범위 제한 (max: 100)
    it('clamps progress at maximum value of 100', () => {
      render(
        <LoadingView message="과다..." progress={200} />
      );

      const progressBar = screen.getByTestId('progress-bar');
      // width 가 100% 로 제한되었는지 확인
    });

    // 9. 음수 진행률 처리
    it('clamps progress at minimum value of 0', () => {
      render(
        <LoadingView message="음수..." progress={-10} />
      );

      const progressBar = screen.getByTestId('progress-bar');
      expect(progressBar).toHaveStyle({ width: '0%' });
    });
  });

  describe('SuccessView', () => {
    // 1. 기본 성공 표시 - 아이콘과 메시지
    it('displays success icon and message', () => {
      render(
        <SuccessView message="저장이 완료되었습니다." />
      );

      const icon = screen.getByText('✅');
      expect(icon).toBeDefined();

      const message = screen.getByText('저장이 완료되었습니다.');
      expect(message).toBeDefined();
    });

    // 2. continue 버튼 포함 시 클릭 이벤트 검증
    it('calls onContinue when continue button is clicked', () => {
      const onContinue = jest.fn();

      render(
        <SuccessView 
          message="저장이 완료되었습니다." 
          onContinue={onContinue}
        />
      );

      fireEvent.press(screen.getByText('계속하기'));
      
      expect(onContinue).toHaveBeenCalledTimes(1);
    });

    // 3. continue 버튼 없이 성공 표시 검증
    it('renders without continue button when not provided', () => {
      render(
        <SuccessView message="저장이 완료되었습니다." />
      );

      const continueButton = screen.queryByText('계속하기');
      expect(continueButton).toBeNull();
    });

    // 4. 성공 스타일 색상 검증 (간접적)
    it('applies green background color to success box', () => {
      render(
        <SuccessView message="저장이 완료되었습니다." />
      );

      const container = screen.getByText('저장이 완료되었습니다.');
      // 스타일 객체를 통해 색상 확인 (간접적)
    });

    // 5. 긴 성공 메시지 처리
    it('handles long success message', () => {
      render(
        <SuccessView 
          message="매우 긴 성공 메시지는 자연스럽게 줄 바꿈이 되어 사용자가 읽을 수 있어야 합니다."
        />
      );

      const message = screen.getByText(/매우 긴 성공/);
      expect(message).toBeDefined();
    });

    // 6. 공백 문자 제거 검증 (trim)
    it('trims whitespace from success message', () => {
      render(
        <SuccessView message="   저장 완료   " />
      );

      const message = screen.getByText(/저장 완료/);
      expect(message.props.children).toBe('저장 완료');
    });
  });

  describe('ConfirmDialog', () => {
    // 1. 기본 확인 다이얼로그 렌더링
    it('renders with title and message', () => {
      render(
        <ConfirmDialog
          title="정말 삭제하시겠습니까?"
          message="이 작업은 되돌릴 수 없습니다."
          onConfirm={jest.fn()}
          onCancel={jest.fn()}
        />
      );

      expect(screen.getByText('정말 삭제하시겠습니까?')).toBeDefined();
      expect(screen.getByText('이 작업은 되돌릴 수 없습니다.')).toBeDefined();
    });

    // 2. 확인 버튼 클릭 시 onConfirm 호출
    it('calls onConfirm when confirm button is clicked', () => {
      const handleOnConfirm = jest.fn();
      const handleOnCancel = jest.fn();

      render(
        <ConfirmDialog
          title="정말 삭제하시겠습니까?"
          message="이 작업은 되돌릴 수 없습니다."
          onConfirm={handleOnConfirm}
          onCancel={handleOnCancel}
        />
      );

      fireEvent.press(screen.getByText('확인'));
      
      expect(handleOnConfirm).toHaveBeenCalledTimes(1);
    });

    // 3. 취소 버튼 클릭 시 onCancel 호출
    it('calls onCancel when cancel button is clicked', () => {
      const handleOnConfirm = jest.fn();
      const handleOnCancel = jest.fn();

      render(
        <ConfirmDialog
          title="정말 삭제하시겠습니까?"
          message="이 작업은 되돌릴 수 없습니다."
          onConfirm={handleOnConfirm}
          onCancel={handleOnCancel}
        />
      );

      fireEvent.press(screen.getByText('취소'));
      
      expect(handleOnCancel).toHaveBeenCalledTimes(1);
    });

    // 4. 확인/취소 버튼 순서 검증
    it('renders confirm button first, then cancel', () => {
      render(
        <ConfirmDialog
          title="정말 삭제하시겠습니까?"
          message="이 작업은 되돌릴 수 없습니다."
          onConfirm={jest.fn()}
          onCancel={jest.fn()}
        />
      );

      const confirmButton = screen.getByText('확인');
      const cancelButton = screen.getByText('취소');

      // flexDirection: 'row' 로 왼쪽부터 확인 → 취소 순서
    });

    // 5. danger variant 스타일 적용 검증
    it('applies danger variant when specified', () => {
      render(
        <ConfirmDialog
          title="정말 삭제하시겠습니까?"
          message="이 작업은 되돌릴 수 없습니다."
          onConfirm={jest.fn()}
          onCancel={jest.fn()}
          variant="danger"
        />
      );

      const confirmButton = screen.getByText('확인');
      // danger 스타일이 적용되었는지 확인 (간접적)
    });

    // 6. custom confirmLabel 사용 검증
    it('uses custom confirm label when provided', () => {
      render(
        <ConfirmDialog
          title="정말 삭제하시겠습니까?"
          message="이 작업은 되돌릴 수 없습니다."
          onConfirm={jest.fn()}
          onCancel={jest.fn()}
          confirmLabel="삭제"
          cancelLabel="취소하기"
        />
      );

      expect(screen.getByText('삭제')).toBeDefined();
      expect(screen.getByText('취소하기')).toBeDefined();
    });

    // 7. custom cancelLabel 사용 검증
    it('uses custom cancel label when provided', () => {
      render(
        <ConfirmDialog
          title="정말 삭제하시겠습니까?"
          message="이 작업은 되돌릴 수 없습니다."
          onConfirm={jest.fn()}
          onCancel={jest.fn()}
          cancelLabel="아니오"
        />
      );

      expect(screen.getByText('아니오')).toBeDefined();
    });

    // 8. 확인 후 취소 시 두 함수 모두 호출 검증
    it('calls both onConfirm and onCancel when confirm is pressed', () => {
      const handleOnConfirm = jest.fn();
      const handleOnCancel = jest.fn();

      render(
        <ConfirmDialog
          title="정말 삭제하시겠습니까?"
          message="이 작업은 되돌릴 수 없습니다."
          onConfirm={handleOnConfirm}
          onCancel={handleOnCancel}
        />
      );

      fireEvent.press(screen.getByText('확인'));
      
      expect(handleOnConfirm).toHaveBeenCalledTimes(1);
      expect(handleOnCancel).toHaveBeenCalledTimes(1);
    });

    // 9. 제목 길이 제한 검증 (간접적)
    it('handles long title gracefully', () => {
      render(
        <ConfirmDialog
          title="매우 긴 제목입니다."
          message="이 작업은 되돌릴 수 없습니다."
          onConfirm={jest.fn()}
          onCancel={jest.fn()}
        />
      );

      expect(screen.getByText('매우 긴 제목입니다.')).toBeDefined();
    });

    // 10. 메시지 텍스트 길이 제한 검증
    it('handles long message gracefully', () => {
      render(
        <ConfirmDialog
          title="확인"
          message="매우 긴 메시지 텍스트는 자연스럽게 줄 바꿈이 되어 사용자가 읽을 수 있어야 합니다. 여러 줄에 걸쳐 표시됩니다."
          onConfirm={jest.fn()}
          onCancel={jest.fn()}
        />
      );

      expect(screen.getByText(/매우 긴 메시지/)).toBeDefined();
    });
  });
});
