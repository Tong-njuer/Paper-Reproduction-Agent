# C++单链表反转

**难度**: medium
**标签**: 链表, 数据结构, C++
**题目ID**: 1

---

## 题目描述

给定一个单链表，请将其反转，并返回反转后的链表头节点。链表节点定义：struct ListNode { int val; ListNode* next; ListNode(int x) : val(x), next(nullptr) {} }; 输入格式：第一行一个整数n，表示链表中节点的个数（0<=n<=5000）。第二行n个整数，表示链表中各节点的值。输出格式：一行，输出反转后链表的各节点值，用空格分隔。示例1：输入5个节点，值为1 2 3 4 5，输出5 4 3 2 1。示例2：输入3个节点，值为10 20 30，输出30 20 10。要求：实现ListNode* reverseList(ListNode* head)函数，时间复杂度O(n)，空间复杂度O(1)，不能使用额外数组存储节点值。

---

## 测试用例

- 用例1: 输入: 5
1 2 3 4 5 → 期望输出: 5 4 3 2 1
- 用例2: 输入: 3
10 20 30 → 期望输出: 30 20 10
- 用例3: 输入: 1
100 → 期望输出: 100
- 用例4: 输入: 0
 → 期望输出: 
- 用例5: 输入: 6
-1 -2 -3 0 1 2 → 期望输出: 2 1 0 -3 -2 -1

---

## 你的代码

```cpp
// 在此编写你的代码

#include <iostream>
using namespace std;

// 链表节点定义
struct ListNode {
    int val;
    ListNode* next;
    ListNode(int x) : val(x), next(nullptr) {}
};

// 反转链表函数 - 使用迭代法
ListNode* reverseList(ListNode* head) {
    // 如果链表为空或只有一个节点，直接返回
    if (head == nullptr || head->next == nullptr) {
        return head;
    }
    
    ListNode* prev = nullptr;  // 前一个节点
    ListNode* curr = head;     // 当前节点
    ListNode* next = nullptr;  // 下一个节点
    
    // 遍历链表，逐个反转节点
    while (curr != nullptr) {
        // 保存下一个节点
        next = curr->next;
        // 反转当前节点的指针
        curr->next = prev;
        // 移动prev和curr指针
        prev = curr;
        curr = next;
    }
    
    // prev现在是新的头节点
    return prev;
}

// 创建链表
ListNode* createList(int n, int* values) {
    if (n == 0) return nullptr;
    
    ListNode* head = new ListNode(values[0]);
    ListNode* current = head;
    
    for (int i = 1; i < n; i++) {
        current->next = new ListNode(values[i]);
        current = current->next;
    }
    
    return head;
}

// 打印链表
void printList(ListNode* head) {
    if (head == nullptr) {
        cout << endl;
        return;
    }
    
    ListNode* current = head;
    while (current != nullptr) {
        cout << current->val;
        if (current->next != nullptr) {
            cout << " ";
        }
        current = current->next;
    }
    cout << endl;
}

// 释放链表内存
void deleteList(ListNode* head) {
    ListNode* current = head;
    while (current != nullptr) {
        ListNode* temp = current;
        current = current->next;
        delete temp;
    }
}

int main() {
    int n;
    cin >> n;
    
    if (n == 0) {
        // 空链表，输出空行
        cout << endl;
        return 0;
    }
    
    int* values = new int[n];
    for (int i = 0; i < n; i++) {
        cin >> values[i];
    }
    
    // 创建链表
    ListNode* head = createList(n, values);
    
    // 反转链表
    ListNode* reversedHead = reverseList(head);
    
    // 输出反转后的链表
    printList(reversedHead);
    
    // 释放内存
    deleteList(reversedHead);
    delete[] values;
    
    return 0;
}


```

---

*此文件由编程教练Agent自动生成 - 请在此文件编写代码，完成后对我说"提交第1题答案"*
