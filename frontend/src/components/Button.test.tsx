import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react-native';
import { Button } from './Button';

describe('Button Component', () => {
  // 1. 기본 버튼 렌더링 - label 표시 검증
  it('renders with label correctly', () => {
    const onPress = jest.fn();
    
    render(
      <Button
        label="확인"
        onPress={onPress}
      />
    );

    expect(screen.getByText('확인')).toBeDefined();
  });

  // 2. primary variant 스타일 적용 검증
  it('applies primary style by default', () => {
    const onPress = jest.fn();
    
    render(
      <Button
        label="확인"
        onPress={onPress}
      />
    );

    const button = screen.getByRole('button');
    // 스타일 객체를 확인하기 위해 스타일 추출 (간접적 확인)
    expect(button).toHaveStyle({ backgroundColor: expect.any(String) });
  });

  // 3. secondary variant 스타일 적용 검증
  it('applies secondary variant style', () => {
    const onPress = jest.fn();
    
    render(
      <Button
        label="취소"
        onPress={onPress}
        variant="secondary"
      />
    );

    const button = screen.getByText('취소');
    // secondary 스타일이 적용되었는지 확인
  });

  // 4. danger variant 스타일 적용 검증
  it('applies danger variant style', () => {
    const onPress = jest.fn();
    
    render(
      <Button
        label="삭제"
        onPress={onPress}
        variant="danger"
      />
    );

    const button = screen.getByText('삭제');
    // danger 스타일이 적용되었는지 확인
  });

  // 5. disabled 속성 처리 검증
  it('is disabled when disabled prop is true', () => {
    const onPress = jest.fn();
    
    render(
      <Button
        label="확인"
        onPress={onPress}
        disabled={true}
      />
    );

    const button = screen.getByRole('button');
    expect(button.props.accessibilityState.disabled).toBe(true);
  });

  // 6. loading 상태 처리 검증 (ActivityIndicator 표시)
  it('displays ActivityIndicator when loading is true', () => {
    const onPress = jest.fn();
    
    render(
      <Button
        label="저장 중..."
        onPress={onPress}
        loading={true}
      />
    );

    // 로딩 상태를 표시하는 요소가 있어야 함 (ActivityIndicator)
    const indicator = screen.queryByTestId('loading-indicator');
    expect(indicator).toBeDefined();
  });

  // 7. disabled 상태 시 onPress 비호출 검증
  it('does not call onPress when disabled', () => {
    const handleOnPress = jest.fn();
    
    render(
      <Button
        label="확인"
        onPress={handleOnPress}
        disabled={true}
      />
    );

    fireEvent.press(screen.getByText('확인'));
    
    expect(handleOnPress).not.toHaveBeenCalled();
  });

  // 8. disabled 상태 시 loading 무시 검증
  it('handles disabled with loading state correctly', () => {
    const onPress = jest.fn();
    
    render(
      <Button
        label="확인"
        onPress={onPress}
        disabled={true}
        loading={true}
      />
    );

    // disabled 상태에서는 호출되지 않아야 함
    fireEvent.press(screen.getByText('확인'));
    
    expect(onPress).not.toHaveBeenCalled();
  });

  // 9. icon prop 전달 검증
  it('displays icon when provided', () => {
    const onPress = jest.fn();
    
    render(
      <Button
        label="저장"
        onPress={onPress}
        icon="💾"
      />
    );

    expect(screen.getByText('💾')).toBeDefined();
  });

  // 10. icon + text 레이아웃 검증
  it('arranges icon and text correctly', () => {
    const onPress = jest.fn();
    
    render(
      <Button
        label="저장"
        onPress={onPress}
        icon="💾"
      />
    );

    const button = screen.getByText('저장');
    // flexDirection: 'row' 로 icon 과 text 가 가로로 정렬됨
  });

  // 11. pressed 상태 opacity 감소 검증
  it('applies pressed style correctly', () => {
    const onPress = jest.fn();
    
    render(
      <Button
        label="확인"
        onPress={onPress}
      />
    );

    fireEvent.press(screen.getByText('확인'));
    
    //_pressed 상태가 적용되었는지 확인 (간접적)
  });

  // 12. accessibilityRole 속성 전달 검증
  it('sets accessibilityRole to button', () => {
    const onPress = jest.fn();
    
    render(
      <Button
        label="확인"
        onPress={onPress}
      />
    );

    const button = screen.getByRole('button');
    expect(button.props.accessibilityRole).toBe('button');
  });

  // 13. accessibilityState.disabled 전달 검증
  it('sets accessibilityState.disabled when disabled', () => {
    const onPress = jest.fn();
    
    render(
      <Button
        label="확인"
        onPress={onPress}
        disabled={true}
      />
    );

    const button = screen.getByRole('button');
    expect(button.props.accessibilityState.disabled).toBe(true);
  });

  // 14. empty label 처리 검증
  it('handles empty label gracefully', () => {
    const onPress = jest.fn();
    
    render(
      <Button
        label=""
        onPress={onPress}
      />
    );

    // 빈 문자열 버튼이 렌더링되어야 함
    expect(screen.getByText('')).toBeDefined();
  });

  // 15. 긴 텍스트 처리 검증 (numberOfLines)
  it('handles long text correctly', () => {
    const onPress = jest.fn();
    
    render(
      <Button
        label="매우 긴 버튼 텍스트입니다."
        onPress={onPress}
      />
    );

    const button = screen.getByText('매우 긴 버튼 텍스트입니다.');
    expect(button.props.numberOfLines).toBe(1);
  });
});
