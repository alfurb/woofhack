#include <iostream>

using namespace std;

int main() {
  int a, b;
  cin >> a >> b;
  cout << a + b;
  int* c = &a;
  delete c;
  return 0;
}
