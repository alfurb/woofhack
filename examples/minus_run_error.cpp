#include <iostream>

using namespace std;

int main() {
  int a, b;
  cin >> a >> b;
  cout << a - b;
  // To make a run time error
  int* c = &a;
  delete c;
  return 0;
}
